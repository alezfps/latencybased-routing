#include <winsock2.h>
#include <ws2tcpip.h>
#include <iostream>
#include <thread>
#include <vector>
#include <chrono>
#include <atomic>

#pragma comment(lib, "ws2_32.lib")

struct Region {
    std::string name;
    std::string ip;
    int port;
};

struct Result {
    std::string name;
    std::string ip;
    int port;
    long latency_ms;
    bool success;
};

long measure_latency(const Region& region, int timeout_ms = 500) {
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) return -1;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(region.port);
    inet_pton(AF_INET, region.ip.c_str(), &addr.sin_addr);

    u_long mode = 1;
    ioctlsocket(sock, FIONBIO, &mode);

    auto start = std::chrono::high_resolution_clock::now();

    connect(sock, (sockaddr*)&addr, sizeof(addr));

    fd_set writeSet;
    FD_ZERO(&writeSet);
    FD_SET(sock, &writeSet);

    timeval tv{};
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;

    int result = select(0, NULL, &writeSet, NULL, &tv);

    auto end = std::chrono::high_resolution_clock::now();

    closesocket(sock);

    if (result > 0) {
        return std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
    }

    return -1;
}

Result probe_region(const Region& region) {
    long latency = measure_latency(region);
    return {
        region.name,
        region.ip,
        region.port,
        latency,
        latency >= 0
    };
}

SOCKET connect_blocking(const Region& region) {
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) return INVALID_SOCKET;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(region.port);
    inet_pton(AF_INET, region.ip.c_str(), &addr.sin_addr);

    if (connect(sock, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
        closesocket(sock);
        return INVALID_SOCKET;
    }

    return sock;
}

int main() {
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);

    std::vector<Region> regions = {
        {"Amsterdam", "0.0.0.0", 1234},
        {"Milan", "0.0.0.0", 1234}
    };

    std::vector<Result> results(regions.size());
    std::vector<std::thread> threads;

    for (size_t i = 0; i < regions.size(); ++i) {
        threads.emplace_back([&, i]() {
            results[i] = probe_region(regions[i]);
            });
    }

    for (auto& t : threads) t.join();
    Result* best = nullptr;
    for (auto& r : results) {
        if (r.success) {
            std::cout << r.name << " latency: " << r.latency_ms << " ms\n";
            if (!best || r.latency_ms < best->latency_ms) {
                best = &r;
            }
        }
    }

    if (!best) {
        std::cout << "No region reachable.\n";
        WSACleanup();
        return 1;
    }

    std::cout << "Connecting to best region: " << best->name << "\n";

    SOCKET sock = connect_blocking({ best->name, best->ip, best->port });
    if (sock == INVALID_SOCKET) {
        std::cout << "Failed to connect.\n";
        WSACleanup();
        return 1;
    }

    std::cout << "Connected. Press ENTER to exit...\n";
    std::string dummy;
    std::getline(std::cin, dummy);

    closesocket(sock);
    WSACleanup();
    return 0;
}