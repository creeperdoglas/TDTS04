#!/usr/bin/env python3
import socket
import threading
import sys

# TROLL_IMAGE_PATH: local file we serve when "Smiley.jpg" is requested
TROLL_IMAGE_PATH = "troll.jpg"

# The port on which our proxy will listen
PROXY_PORT = 8001

def read_http_headers(sock):
    """
    Reads HTTP headers from 'sock', stopping at the first blank line.
    Returns a list of decoded lines (header lines).
    Returns an empty list if socket closes before any headers are read.
    """
    headers = []
    while True:
        line = read_line(sock)
        if not line:
            # Either connection closed or got empty line
            break
        stripped = line.strip('\r\n')
        if stripped == "":
            # Blank line -> end of headers
            break
        headers.append(stripped)
    return headers

def read_line(sock):
    """
    Read one line (until '\n') from the socket or return None if EOF.
    """
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            if len(data) == 0:
                return None
            break
        data += chunk
        if data.endswith(b'\n'):
            break
    return data.decode('utf-8', errors='replace')

def forward_raw(sock_in, sock_out, length=None):
    """
    Forward raw bytes from sock_in to sock_out.
    If length is specified, read exactly that many bytes.
    Otherwise, read until EOF from sock_in.
    """
    BUFSIZE = 4096
    if length is not None:
        remaining = length
        while remaining > 0:
            chunk = sock_in.recv(min(BUFSIZE, remaining))
            if not chunk:
                break
            sock_out.sendall(chunk)
            remaining -= len(chunk)
    else:
        # read until EOF
        while True:
            chunk = sock_in.recv(BUFSIZE)
            if not chunk:
                break
            sock_out.sendall(chunk)

def handle_client(client_conn, client_addr):
    print(f"[{client_addr}] Handling new connection.")

    # 1) Read request headers from the client
    request_headers = read_http_headers(client_conn)
    if not request_headers:
        # No headers means client likely disconnected immediately
        client_conn.close()
        print(f"[{client_addr}] No request received. Connection closed.")
        return

    # 2) Parse the first request line, e.g. "GET http://example.com/ HTTP/1.1"
    request_line = request_headers[0]
    method, url_or_path, http_version = parse_request_line(request_line)
    if method is None:
        send_http_error(client_conn, 400, "Bad Request")
        client_conn.close()
        print(f"[{client_addr}] Malformed request line. Connection closed.")
        return

    # 3) Convert remaining headers into a dict (lowercase keys)
    header_dict = {}
    for h in request_headers[1:]:
        parts = h.split(":", 1)
        if len(parts) == 2:
            k, v = parts[0].strip(), parts[1].strip()
            header_dict[k.lower()] = v

    # 4) Extract the host, port, and the actual path (stripping "http://...")
    remote_host, remote_port, path = extract_host_port_path(url_or_path, header_dict)
    print(f"[DEBUG] remote_host={remote_host}, remote_port={remote_port}, path={path}")

    # 5) Only handle GET
    if method.upper() != "GET":
        send_http_error(client_conn, 501, "Not Implemented")
        client_conn.close()
        print(f"[{client_addr}] Method {method} not supported.")
        return

    # 6) Special case: If path ends with "Smiley.jpg", serve local troll image
    if path.lower().endswith("smiley.jpg"):
        serve_local_image(client_conn, http_version, TROLL_IMAGE_PATH)
        client_conn.close()
        print(f"[{client_addr}] Served troll image for Smiley.jpg request.")
        return

    # 7) Build a new request to send to the remote server
    #    We'll use HTTP/1.1 so we don't forcibly downgrade. 
    out_headers = []
    out_headers.append(f"{method} {path} HTTP/1.1")
    out_headers.append(f"Host: {remote_host}")
    # If you want to force close:
    # out_headers.append("Connection: close")

    # 8) Forward other relevant headers, except Proxy-Connection. 
    #    If you want to skip "Connection:" entirely, you can do so; 
    #    here we keep it for potential keep-alive benefits.
    for line in request_headers[1:]:
        lower = line.lower()
        if lower.startswith("proxy-connection"):
            continue
        # if you wanted to skip any "Connection:" from the client, uncomment:
        # elif lower.startswith("connection"):
        #     continue
        else:
            out_headers.append(line)

    # 9) Final request string to server
    out_req = "\r\n".join(out_headers) + "\r\n\r\n"
    # Debug print if needed:
    # print("[DEBUG] Outgoing request:\n" + out_req)

    # 10) Connect to remote server
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect((remote_host, remote_port))
    except Exception as e:
        print(f"[{client_addr}] Could not connect to {remote_host}:{remote_port} - {e}")
        send_http_error(client_conn, 502, "Bad Gateway")
        client_conn.close()
        return

    # 11) Send the request to the server
    server_socket.sendall(out_req.encode('utf-8'))

    # 12) Read the response headers from the server
    response_headers = read_http_headers(server_socket)
    if not response_headers:
        # The server closed or sent nothing
        server_socket.close()
        client_conn.close()
        print(f"[{client_addr}] Server closed without sending headers.")
        return

    # 13) Parse the first response line (status) and build a dict of headers
    resp_status_line = response_headers[0]
    resp_header_dict = {}
    for h in response_headers[1:]:
        parts = h.split(":", 1)
        if len(parts) == 2:
            k = parts[0].strip().lower()
            v = parts[1].strip()
            resp_header_dict[k] = v

    # 14) Check for content-length, chunked, etc.
    content_length = None
    is_chunked = False
    content_encoding = resp_header_dict.get("content-encoding", "").lower()
    content_type = resp_header_dict.get("content-type", "").lower()

    if "content-length" in resp_header_dict:
        try:
            content_length = int(resp_header_dict["content-length"])
        except:
            content_length = None

    if "transfer-encoding" in resp_header_dict and "chunked" in resp_header_dict["transfer-encoding"].lower():
        is_chunked = True

    # 15) Reconstruct response headers
    out_resp_headers = []
    out_resp_headers.append(resp_status_line)

    skip_headers = set(["transfer-encoding"])  # We'll handle chunked logic ourselves
    for k, v in resp_header_dict.items():
        if k in skip_headers:
            continue
        if k == "content-length":
            # We'll add it later if we do modifications
            continue
        # Otherwise, forward the header as-is
        out_resp_headers.append(f"{k}: {v}")

    # 16) Decide whether to do text replacements or forward raw
    body_data = b""

    if (not is_chunked) and (content_encoding == "") and ("text" in content_type):
        # => Attempt to read entire body and do replacements
        if content_length is not None:
            body_data = read_exact(server_socket, content_length)
        else:
            body_data = read_until_eof(server_socket)

        # Simple replacements
        try:
            text_str = body_data.decode('utf-8', errors='replace')
            text_str = text_str.replace("Smiley", "Trolly")
            text_str = text_str.replace("Stockholm", "Linköping")
            body_data = text_str.encode('utf-8')
        except Exception:
            # if decode fails, keep the original body_data
            pass

        # Add a new Content-Length
        new_len = len(body_data)
        out_resp_headers.append(f"Content-Length: {new_len}")

    else:
        # Forward raw, no replacements
        if is_chunked:
            out_resp_headers.append("Transfer-Encoding: chunked")
        elif content_length is not None:
            out_resp_headers.append(f"Content-Length: {content_length}")

    # 17) End headers with a blank line
    out_resp_headers.append("")
    out_resp_headers_raw = "\r\n".join(out_resp_headers).encode('utf-8')

    # 18) Send headers to the client
    client_conn.sendall(out_resp_headers_raw)

    # 19) Forward the body
    if (not is_chunked) and (content_encoding == "") and ("text" in content_type):
        # We have the modified body in memory
        client_conn.sendall(body_data)
    else:
        # Just forward raw from server to client
        if content_length is not None:
            forward_raw(server_socket, client_conn, content_length)
        else:
            forward_raw(server_socket, client_conn, None)

    # 20) Close both sockets
    server_socket.close()
    client_conn.close()
    print(f"[{client_addr}] Done. Connection closed.")

def parse_request_line(line):
    """
    Parse the first request line, e.g. 'GET http://example.com/ HTTP/1.1'.
    Returns (method, url_or_path, http_version) or (None, None, None) if malformed.
    """
    parts = line.split()
    if len(parts) != 3:
        return None, None, None
    return parts[0], parts[1], parts[2]

def extract_host_port_path(url_or_path, header_dict):
    """
    If url_or_path is full, like 'http://host:port/path', strip off 'http://host:port'.
    Return (host, port, path) with default port 80 if none found.
    If it's just a path, we read the host from the 'Host:' header.
    """
    default_port = 80
    if url_or_path.lower().startswith("http://"):
        # strip off 'http://'
        tmp = url_or_path[7:]
        slash_pos = tmp.find('/')
        if slash_pos == -1:
            host_part = tmp
            path_part = "/"
        else:
            host_part = tmp[:slash_pos]
            path_part = tmp[slash_pos:]  # includes '/'
        # check if host_part has ':port'
        if ':' in host_part:
            host, port_str = host_part.split(':', 1)
            try:
                port = int(port_str)
            except:
                port = default_port
        else:
            host = host_part
            port = default_port
        return host, port, path_part
    else:
        # It's possibly a relative path like "/something"
        # We'll look at the Host header to see which server to contact
        host_header = header_dict.get("host", "")
        host = host_header
        port = default_port
        if ':' in host_header:
            h, p_str = host_header.split(':', 1)
            host = h
            try:
                port = int(p_str)
            except:
                port = default_port
        path_part = url_or_path
        if not path_part.startswith("/"):
            path_part = "/" + path_part
        return host, port, path_part

def send_http_error(sock, code, message):
    """
    Send a minimal HTTP error response, then flush/close.
    """
    body = f"<html><body><h2>{code} {message}</h2></body></html>"
    resp = (
        f"HTTP/1.1 {code} {message}\r\n"
        "Content-Type: text/html\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
        f"{body}"
    )
    sock.sendall(resp.encode('utf-8'))

def read_exact(sock, length):
    """
    Read exactly 'length' bytes from sock.
    """
    data = b""
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            break
        data += chunk
        remaining -= len(chunk)
    return data

def read_until_eof(sock):
    """
    Read until the socket is closed (EOF).
    """
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data

def serve_local_image(client_sock, http_version, filepath):
    """
    Serve a local file (image) if we intercept a request for "Smiley.jpg".
    """
    try:
        with open(filepath, "rb") as f:
            img_data = f.read()
        # Send a 200 OK response
        resp_headers = (
            f"{http_version} 200 OK\r\n"
            "Content-Type: image/jpeg\r\n"
            f"Content-Length: {len(img_data)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        client_sock.sendall(resp_headers.encode('utf-8'))
        client_sock.sendall(img_data)
    except FileNotFoundError:
        # Send 404 if troll.jpg not found
        body = "<html><body><h2>404 Not Found</h2></body></html>"
        resp = (
            f"{http_version} 404 Not Found\r\n"
            "Content-Type: text/html\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
            f"{body}"
        )
        client_sock.sendall(resp.encode('utf-8'))

def main():
    # Create a listening socket
    proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        proxy_socket.bind(("0.0.0.0", PROXY_PORT))
    except Exception as e:
        print(f"Could not bind on port {PROXY_PORT}: {e}")
        sys.exit(1)

    proxy_socket.listen(5)
    print(f"[MAIN] Proxy listening on port {PROXY_PORT}...")

    while True:
        client_conn, client_addr = proxy_socket.accept()
        t = threading.Thread(target=handle_client, args=(client_conn, client_addr))
        t.daemon = True
        t.start()

if __name__ == "__main__":
    main()
