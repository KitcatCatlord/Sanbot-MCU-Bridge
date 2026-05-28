#include "usb-send.h"

#ifdef __APPLE__
#include "/opt/homebrew/include/libusb-1.0/libusb.h"
#else
#include <libusb-1.0/libusb.h>
#endif
#include <chrono>
#include <stdexcept>
#include <thread>
#include <utility>
using namespace std;

SanbotUsbManager::SanbotUsbManager() {
    if (libusb_init(&ctx) != 0) {
        throw runtime_error("libusb_init failed");
    }
    running = true;
    worker = thread(&SanbotUsbManager::sendLoop, this);
}

SanbotUsbManager::~SanbotUsbManager() {
    stopListener();
    running = false;
    cv.notify_all();
    queueEmptyCv.notify_all();
    if (worker.joinable()) worker.join();
    lock_guard<mutex> lock(usbMtx);
    closeDevice(bottom);
    closeDevice(head);
    libusb_exit(ctx);
}

void SanbotUsbManager::sendToHead(const vector<unsigned char>& frame) {
    enqueueMessage(WHAT_SEND_TO_HEAD, frame);
}

void SanbotUsbManager::sendToBottom(const vector<unsigned char>& frame) {
    enqueueMessage(WHAT_SEND_TO_BOTTOM, frame);
}

void SanbotUsbManager::sendToPoint(const vector<unsigned char>& routedFrameWithTag) {
    enqueueMessage(WHAT_SEND_TO_POINT, routedFrameWithTag);
}

void SanbotUsbManager::enqueueMessage(int what, const vector<unsigned char>& data) {
    lock_guard<mutex> lock(mtx);
    msgQueue.push(Message{what, data});
    cv.notify_one();
}

bool SanbotUsbManager::takeControl() {
    lock_guard<mutex> lock(usbMtx);
    openDevice(head, PID_HEAD);
    openDevice(bottom, PID_BOTTOM);
    return (head.handle && head.outEp != 0) || (bottom.handle && bottom.outEp != 0);
}

void SanbotUsbManager::setListener(UsbListener callback) {
    lock_guard<mutex> lock(listenerMtx);
    listener = std::move(callback);
}

void SanbotUsbManager::startListener() {
    if (listening.exchange(true)) return;
    listenerWorker = thread(&SanbotUsbManager::listenLoop, this);
}

void SanbotUsbManager::stopListener() {
    if (!listening.exchange(false)) return;
    if (listenerWorker.joinable()) listenerWorker.join();
}

void SanbotUsbManager::sendLoop() {
    while (true) {
        Message msg;
        {
            unique_lock<mutex> lock(mtx);
            cv.wait(lock, [&] { return !msgQueue.empty() || !running; });
            if (msgQueue.empty() && !running) break;
            if (msgQueue.empty()) continue;
            msg = msgQueue.front();
            msgQueue.pop();
            activeMessages++;
        }

        switch (msg.what) {
            case WHAT_SEND_TO_HEAD:
                sendBufferTo(head, PID_HEAD, msg.data);
                break;
            case WHAT_SEND_TO_BOTTOM:
                sendBufferTo(bottom, PID_BOTTOM, msg.data);
                break;
            case WHAT_SEND_TO_POINT:
                handlePointMessage(msg.data);
                break;
            default:
                break;
        }

        {
            lock_guard<mutex> lock(mtx);
            if (activeMessages > 0) activeMessages--;
            if (msgQueue.empty() && activeMessages == 0) notifyIdle();
        }
    }
}

void SanbotUsbManager::handlePointMessage(const vector<unsigned char>& buffers) {
    if (buffers.size() < 2) return;
    unsigned char tag = buffers.back();
    vector<unsigned char> temp(buffers.begin(), buffers.end() - 1);

    switch (tag) {
        case 0x01:
            sendBufferTo(head, PID_HEAD, temp);
            break;
        case 0x02:
            sendBufferTo(bottom, PID_BOTTOM, temp);
            break;
        case 0x03:
            sendBufferTo(head, PID_HEAD, temp);
            sendBufferTo(bottom, PID_BOTTOM, temp);
            break;
        default:
            break;
    }
}

void SanbotUsbManager::sendBufferTo(EndpointSet& dev, uint16_t pid, const vector<unsigned char>& buf) {
    if (buf.empty()) return;

    lock_guard<mutex> lock(usbMtx);
    if (!dev.handle || dev.outEp == 0) {
        openDevice(dev, pid);
    }

    if (!dev.handle || dev.outEp == 0) {
        dev.failCount++;
        if (dev.failCount % 10 == 0) {
            closeDevice(dev);
            openDevice(dev, pid);
        }
        return;
    }

    int transferred = 0;
    int r = libusb_bulk_transfer(
        dev.handle,
        dev.outEp,
        const_cast<unsigned char*>(buf.data()),
        (int)buf.size(),
        &transferred,
        0
    );

    if (r < 0 || transferred <= 0) {
        dev.failCount++;
        if (dev.failCount % 10 == 0) {
            closeDevice(dev);
            openDevice(dev, pid);
        }
    } else {
        dev.failCount = 0;
    }
}

void SanbotUsbManager::listenLoop() {
    while (listening) {
        bool received = false;
        {
            lock_guard<mutex> lock(usbMtx);
            received = pollEndpoint(head, PID_HEAD) || received;
            received = pollEndpoint(bottom, PID_BOTTOM) || received;
        }
        if (!received) {
            this_thread::sleep_for(chrono::milliseconds(5));
        }
    }
}

bool SanbotUsbManager::pollEndpoint(EndpointSet& dev, uint16_t pid) {
    if (!dev.handle || dev.inEp == 0) {
        openDevice(dev, pid);
    }
    if (!dev.handle || dev.inEp == 0) {
        return false;
    }

    vector<unsigned char> buf(512);
    int transferred = 0;
    int r = libusb_bulk_transfer(
        dev.handle,
        dev.inEp,
        buf.data(),
        static_cast<int>(buf.size()),
        &transferred,
        25
    );

    if (r == LIBUSB_ERROR_TIMEOUT || transferred <= 0) {
        return false;
    }

    if (r < 0) {
        dev.failCount++;
        if (dev.failCount % 10 == 0) {
            closeDevice(dev);
            openDevice(dev, pid);
        }
        return false;
    }

    dev.failCount = 0;
    buf.resize(static_cast<size_t>(transferred));

    UsbListener callback;
    {
        lock_guard<mutex> lock(listenerMtx);
        callback = listener;
    }
    if (callback) {
        callback(pid, buf);
    }
    return true;
}

void SanbotUsbManager::openDevice(EndpointSet& dev, uint16_t pid) {
    closeDevice(dev);

    libusb_device** list = nullptr;
    ssize_t cnt = libusb_get_device_list(ctx, &list);
    if (cnt < 0) return;

    for (ssize_t i = 0; i < cnt; ++i) {
        libusb_device* device = list[i];
        libusb_device_descriptor desc;
        if (libusb_get_device_descriptor(device, &desc) != 0) continue;
        if (desc.idVendor != VID || desc.idProduct != pid) continue;

        libusb_device_handle* handle = nullptr;
        if (libusb_open(device, &handle) != 0 || !handle) continue;

        libusb_set_auto_detach_kernel_driver(handle, 1);

        libusb_config_descriptor* config = nullptr;
        if (libusb_get_active_config_descriptor(device, &config) != 0) {
            libusb_close(handle);
            continue;
        }

        bool found = false;
        for (uint8_t ifnum = 0; ifnum < config->bNumInterfaces && !found; ++ifnum) {
            const libusb_interface& iface = config->interface[ifnum];
            for (int alt = 0; alt < iface.num_altsetting && !found; ++alt) {
                const libusb_interface_descriptor& ifdesc = iface.altsetting[alt];
                uint8_t outEp = 0;
                uint8_t inEp = 0;
                for (uint8_t e = 0; e < ifdesc.bNumEndpoints; ++e) {
                    const libusb_endpoint_descriptor& ep = ifdesc.endpoint[e];
                    if ((ep.bmAttributes & LIBUSB_TRANSFER_TYPE_MASK) == LIBUSB_TRANSFER_TYPE_BULK) {
                        if (ep.bEndpointAddress & LIBUSB_ENDPOINT_IN) {
                            inEp = ep.bEndpointAddress;
                        } else {
                            outEp = ep.bEndpointAddress;
                        }
                    }
                }
                if (outEp != 0) {
                    if (claimInterface(handle, ifdesc.bInterfaceNumber)) {
                        dev.handle = handle;
                        dev.outEp = outEp;
                        dev.inEp = inEp;
                        dev.iface = ifdesc.bInterfaceNumber;
                        dev.failCount = 0;
                        libusb_clear_halt(handle, outEp);
                        if (inEp != 0) libusb_clear_halt(handle, inEp);
                        found = true;
                    }
                }
            }
        }

        libusb_free_config_descriptor(config);

        if (!found) {
            libusb_close(handle);
        } else {
            break;
        }
    }

    libusb_free_device_list(list, 1);
}

bool SanbotUsbManager::claimInterface(libusb_device_handle* handle, int iface) {
    int active = libusb_kernel_driver_active(handle, iface);
    if (active == 1) {
        libusb_detach_kernel_driver(handle, iface);
    }

    int rc = libusb_claim_interface(handle, iface);
    if (rc == 0) return true;

    if (rc == LIBUSB_ERROR_BUSY) {
        libusb_detach_kernel_driver(handle, iface);
        rc = libusb_claim_interface(handle, iface);
        if (rc == 0) return true;

        libusb_reset_device(handle);
        rc = libusb_claim_interface(handle, iface);
    }

    return rc == 0;
}

void SanbotUsbManager::closeDevice(EndpointSet& dev) {
    if (dev.handle) {
        if (dev.iface >= 0) {
            libusb_release_interface(dev.handle, dev.iface);
        }
        libusb_close(dev.handle);
    }
    dev.handle = nullptr;
    dev.outEp = 0;
    dev.inEp = 0;
    dev.iface = -1;
    dev.failCount = 0;
}

void SanbotUsbManager::notifyIdle() {
    queueEmptyCv.notify_all();
}

void SanbotUsbManager::waitForPendingSends() {
    unique_lock<mutex> lock(mtx);
    queueEmptyCv.wait(lock, [&] { return msgQueue.empty() && activeMessages == 0; });
}
