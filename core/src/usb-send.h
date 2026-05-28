#pragma once

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <mutex>
#include <queue>
#include <thread>
#include <vector>

using namespace std;

struct libusb_device_handle;
struct libusb_context;
struct libusb_device;
struct libusb_config_descriptor;
struct libusb_interface;
struct libusb_interface_descriptor;
struct libusb_endpoint_descriptor;

class SanbotUsbManager {
public:
    using UsbListener = function<void(uint16_t pid, const vector<unsigned char>& data)>;

    static constexpr uint16_t VID = 0x0483;
    static constexpr uint16_t PID_BOTTOM = 0x5740;
    static constexpr uint16_t PID_HEAD   = 0x5741;

    static constexpr int WHAT_SEND_TO_HEAD   = 0x01;
    static constexpr int WHAT_SEND_TO_BOTTOM = 0x02;
    static constexpr int WHAT_SEND_TO_POINT  = 0x04;

    SanbotUsbManager();
    ~SanbotUsbManager();

    void sendToHead(const vector<unsigned char>& frame);
    void sendToBottom(const vector<unsigned char>& frame);
    void sendToPoint(const vector<unsigned char>& routedFrameWithTag);
    void waitForPendingSends();
    bool takeControl();
    void setListener(UsbListener callback);
    void startListener();
    void stopListener();

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
        vector<unsigned char> data;
    };

    libusb_context* ctx = nullptr;
    EndpointSet bottom;
    EndpointSet head;

    thread worker;
    thread listenerWorker;
    mutex mtx;
    mutex usbMtx;
    mutex listenerMtx;
    condition_variable cv;
    condition_variable queueEmptyCv;
    queue<Message> msgQueue;
    size_t activeMessages = 0;
    atomic<bool> running{false};
    atomic<bool> listening{false};
    UsbListener listener;

    void enqueueMessage(int what, const vector<unsigned char>& data);
    void sendLoop();
    void listenLoop();
    void handlePointMessage(const vector<unsigned char>& buffers);
    void sendBufferTo(EndpointSet& dev, uint16_t pid, const vector<unsigned char>& buf);
    bool pollEndpoint(EndpointSet& dev, uint16_t pid);
    void openDevice(EndpointSet& dev, uint16_t pid);
    void closeDevice(EndpointSet& dev);
    bool claimInterface(libusb_device_handle* handle, int iface);
    void notifyIdle();
};
