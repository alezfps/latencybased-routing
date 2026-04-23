#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>
#include <unistd.h>
#include <vector>

#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <sys/types.h>

namespace {
constexpr size_t kBufferSize = 4096;

bool parse_args(int argc,
                char** argv,
                std::string& host,
                int& port,
                std::string& client_id,
                std::string& payload) {
  if (argc != 5) {
    std::cerr << "Usage: ./latency_client <router_host> <router_port> <client_id> <payload>\n";
    return false;
  }

  host = argv[1];
  try {
    port = std::stoi(argv[2]);
  } catch (const std::exception&) {
    std::cerr << "Invalid router_port: " << argv[2] << "\n";
    return false;
  }
  client_id = argv[3];
  payload = argv[4];

  return true;
}

int connect_tcp(const std::string& host, int port) {
  struct addrinfo hints {};
  struct addrinfo* res = nullptr;
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;

  const std::string port_str = std::to_string(port);
  const int status = getaddrinfo(host.c_str(), port_str.c_str(), &hints, &res);
  if (status != 0) {
    std::cerr << "getaddrinfo failed: " << gai_strerror(status) << "\n";
    return -1;
  }

  int sockfd = -1;
  for (auto* p = res; p != nullptr; p = p->ai_next) {
    sockfd = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
    if (sockfd < 0) {
      continue;
    }
    if (connect(sockfd, p->ai_addr, p->ai_addrlen) == 0) {
      break;
    }
    close(sockfd);
    sockfd = -1;
  }

  freeaddrinfo(res);
  return sockfd;
}
}  // namespace

int main(int argc, char** argv) {
  std::string host;
  int port;
  std::string client_id;
  std::string payload;
  if (!parse_args(argc, argv, host, port, client_id, payload)) {
    return 1;
  }

  int sockfd = connect_tcp(host, port);
  if (sockfd < 0) {
    std::cerr << "Failed to connect to router at " << host << ":" << port << "\n";
    return 1;
  }

  std::string request =
      "{\"clientId\":\"" + client_id + "\",\"payload\":\"" + payload + "\"}\n";
  const ssize_t sent = send(sockfd, request.c_str(), request.size(), 0);
  if (sent < 0) {
    std::cerr << "Failed to send request: " << std::strerror(errno) << "\n";
    close(sockfd);
    return 1;
  }

  std::vector<char> buffer(kBufferSize);
  const ssize_t received = recv(sockfd, buffer.data(), buffer.size() - 1, 0);
  if (received < 0) {
    std::cerr << "Failed to receive response: " << std::strerror(errno) << "\n";
    close(sockfd);
    return 1;
  }

  buffer[received] = '\0';
  std::cout << "Router response: " << buffer.data();
  close(sockfd);
  return 0;
}
