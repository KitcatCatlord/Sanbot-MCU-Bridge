#ifdef __APPLE__
#include "/opt/homebrew/include/libusb-1.0/libusb.h"
#else
#include <libusb-1.0/libusb.h>
#endif
#include <thread>
#include <mutex>
#include <condition_variable>
#include <queue>
#include <vector>
#include <cstdint>
#include <atomic>
#include <stdexcept>

using namespace std;

class SanbotUsbManager {
public:
    static constexpr uint16_t VID = 0x0483;
    static constexpr uint16_t PID_BOTTOM = 0x5740;
    static constexpr uint16_t PID_HEAD   = 0x5741;

    static constexpr int WHAT_SEND_TO_HEAD   = 0x01;
    static constexpr int WHAT_SEND_TO_BOTTOM = 0x02;
    static constexpr int WHAT_SEND_TO_POINT  = 0x04;

    SanbotUsbManager() {
        if (libusb_init(&ctx) != 0) {
            throw runtime_error("libusb_init failed");
        }
        running = true;
        worker = thread(&SanbotUsbManager::sendLoop, this);
    }

    ~SanbotUsbManager() {
        running = false;
        cv.notify_all();
        if (worker.joinable()) worker.join();
        closeDevice(bottom);
        closeDevice(head);
        libusb_exit(ctx);
    }

    void sendToHead(const vector<unsigned char>& frame) {
        enqueueMessage(WHAT_SEND_TO_HEAD, frame);
    }

    void sendToBottom(const vector<unsigned char>& frame) {
        enqueueMessage(WHAT_SEND_TO_BOTTOM, frame);
    }

    void sendToPoint(const vector<unsigned char>& routedFrameWithTag) {
        enqueueMessage(WHAT_SEND_TO_POINT, routedFrameWithTag);
    }

private:
    struct EndpointSet {
        libusb_device_handle* handle = nullptr;
        uint8_t outEp = 0;
        uint8_t inEp  = 0;
        int iface = -1;
        int failCount = 0;
    };

    struct Message {
        int what;
        vector<uint8_t> data;
    };

    libusb_context* ctx = nullptr;
    EndpointSet bottom;
    EndpointSet head;

    thread worker;
    mutex mtx;
    condition_variable cv;
    queue<Message> msgQueue;
    atomic<bool> running{false};

    void enqueueMessage(int what, const vector<uint8_t>& data) {
        lock_guard<mutex> lock(mtx);
        msgQueue.push(Message{what, data});
        cv.notify_one();
    }

    void sendLoop() {
        while (running) {
            Message msg;
            {
                unique_lock<mutex> lock(mtx);
                cv.wait(lock, [&] { return !msgQueue.empty() || !running; });
                if (!running) break;
                msg = msgQueue.front();
                msgQueue.pop();
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
        }
    }

    void handlePointMessage(const vector<uint8_t>& buffers) {
        if (buffers.size() < 2) return;
        uint8_t tag = buffers.back();
        vector<uint8_t> temp(buffers.begin(), buffers.end() - 1);

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

    void sendBufferTo(EndpointSet& dev, uint16_t pid, const vector<uint8_t>& buf) {
        if (buf.empty()) return;

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

    void openDevice(EndpointSet& dev, uint16_t pid) {
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
                        int kd = libusb_kernel_driver_active(handle, ifdesc.bInterfaceNumber);
                        if (kd == 1) {
                            libusb_detach_kernel_driver(handle, ifdesc.bInterfaceNumber);
                        }
                        if (libusb_claim_interface(handle, ifdesc.bInterfaceNumber) == 0) {
                            dev.handle = handle;
                            dev.outEp = outEp;
                            dev.inEp = inEp;
                            dev.iface = ifdesc.bInterfaceNumber;
                            dev.failCount = 0;
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

    void closeDevice(EndpointSet& dev) {
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
};
