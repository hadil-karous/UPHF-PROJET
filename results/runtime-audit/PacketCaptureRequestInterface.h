#ifndef PACKETCAPTUREREQUESTINTERFACE_H_
#define PACKETCAPTUREREQUESTINTERFACE_H_

#include <vanetza/dcc/interface.hpp>
#include <vanetza/net/chunk_packet.hpp>
#include <vanetza/net/osi_layer.hpp>
#include <vanetza/common/byte_buffer.hpp>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <iostream>

namespace artery
{

// Capture le paquet complet (GeoNet + BTP + payload) apres encodage Vanetza.
// Distingue CAM/CPM par le port destination BTP-B lu dans le buffer :
//   2001 (CAM) -> UDP camPort (9301+idx)
//   2002 (CPM) -> UDP cpmPort (camPort+300 = 9601+idx)
// offset BTP dst port = GeoNet 4 + 8 + SHB 28 = 40
class PacketCaptureRequestInterface : public vanetza::dcc::RequestInterface
{
public:
    static constexpr std::size_t BTP_DPORT_OFFSET = 40;
    static constexpr uint16_t BTP_PORT_CAM = 2001;
    static constexpr uint16_t BTP_PORT_CPM = 2009;
    static constexpr int CPM_PORT_SHIFT = 300;

    PacketCaptureRequestInterface(vanetza::dcc::RequestInterface* inner, int udp_port)
        : mInner(inner), mCamPort(udp_port), mCpmPort(udp_port + CPM_PORT_SHIFT)
    {
        mSock = socket(AF_INET, SOCK_DGRAM, 0);
        if (mSock >= 0) {
            memset(&mCamAddr, 0, sizeof(mCamAddr));
            mCamAddr.sin_family = AF_INET;
            mCamAddr.sin_port = htons(mCamPort);
            mCamAddr.sin_addr.s_addr = inet_addr("127.0.0.1");

            memset(&mCpmAddr, 0, sizeof(mCpmAddr));
            mCpmAddr.sin_family = AF_INET;
            mCpmAddr.sin_port = htons(mCpmPort);
            mCpmAddr.sin_addr.s_addr = inet_addr("127.0.0.1");
        }
    }

    ~PacketCaptureRequestInterface() {
        if (mSock >= 0) close(mSock);
    }

    void request(const vanetza::dcc::DataRequest& req,
                 std::unique_ptr<vanetza::ChunkPacket> packet) override
    {
        vanetza::ByteBuffer buf;
        for (auto layer : vanetza::osi_layers) {
            vanetza::ByteBuffer layer_buf;
            (*packet)[layer].convert(layer_buf);
            buf.insert(buf.end(), layer_buf.begin(), layer_buf.end());
        }

        if (!buf.empty() && mSock >= 0) {
            const struct sockaddr_in* dest = &mCamAddr;
            const char* kind = "CAM";
            int port = mCamPort;
            if (buf.size() >= BTP_DPORT_OFFSET + 2) {
                uint16_t dport = (static_cast<uint16_t>(buf[BTP_DPORT_OFFSET]) << 8)
                               |  static_cast<uint16_t>(buf[BTP_DPORT_OFFSET + 1]);
                if (dport == BTP_PORT_CPM) {
                    dest = &mCpmAddr; kind = "CPM"; port = mCpmPort;
                }
            }
            sendto(mSock, buf.data(), buf.size(), 0,
                   (struct sockaddr*)dest, sizeof(*dest));
            std::cout << "PacketCapture: " << kind << " " << buf.size()
                      << " bytes -> UDP " << port << std::endl;
        }

        mInner->request(req, std::move(packet));
    }

private:
    vanetza::dcc::RequestInterface* mInner;
    int mCamPort;
    int mCpmPort;
    int mSock = -1;
    struct sockaddr_in mCamAddr{};
    struct sockaddr_in mCpmAddr{};
};

} // namespace artery

#endif
