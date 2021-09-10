import socket


def communicate(host, port, request: str):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, int(port)))
    s.send(request.encode())
    response = s.recv(1024).decode()
    s.close()
    return response
