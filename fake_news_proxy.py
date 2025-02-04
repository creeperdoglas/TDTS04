#!/usr/bin/env python3
import socket
import threading
import sys
#note, some comments have been added by ai, code however is fully manually written.
# This is the local file we serve when someone requests "Smiley.jpg"
TROLL_IMAGE_PATH = "troll.jpg"

# The port on which our proxy will listen
PROXY_PORT = 8888

# A simple function to read HTTP headers from a socket.
# Returns a list of decoded lines (not including the final blank line).
def read_http_headers(sock):
    """
    Reads HTTP headers from `sock`, stopping at the first blank line.
    Returns a list of strings (header lines).
    Returns an empty list if socket closes before any headers are read.
    """
    headers = []
    # We read line by line until we hit a blank line.
    while True:
        line = read_line(sock)
        if not line:
            # Either connection closed or we got an empty line
            break
        stripped = line.strip('\r\n')
        if stripped == "":
            # Blank line -> end of headers
            break
        headers.append(stripped)
    return headers

def read_line(sock):
    """
    Read until we get a '\n' from the socket or no data at all.
    Return the line (including \r\n), or None if EOF.
    """
    data = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            # EOF
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
    If length is None, read until EOF. Otherwise, read exactly `length` bytes.
    """
    BUFSIZE = 4096
    if length is not None:
        # Read exactly length bytes
        remaining = length
        while remaining > 0:
            chunk = sock_in.recv(min(BUFSIZE, remaining))
            if not chunk:
                break
            sock_out.sendall(chunk)
            remaining -= len(chunk)
    else:
        # Read until EOF
        while True:
            chunk = sock_in.recv(BUFSIZE)
            if not chunk:
                break
            sock_out.sendall(chunk)

def handle_client(client_conn, client_addr):
    """
    Handle a single client connection:
      1) Parse request
      2) Connect to remote server if needed
      3) Forward request, read response
      4) Possibly modify response
      5) Send response back to client
    """
    print(f"[{client_addr}] Handling new connection.")

    request_headers = read_http_headers(client_conn)
    if not request_headers:
        # No headers means the client likely disconnected immediately
        client_conn.close()
        print(f"[{client_addr}] No request received. Connection closed.")
        return

    # Parse the first request line, e.g. "GET http://example.com/ HTTP/1.1"
    request_line = request_headers[0]
    method, url_or_path, http_version = parse_request_line(request_line)
    if method is None:
        # Malformed
        send_http_error(client_conn, 400, "Bad Request")
        client_conn.close()
        print(f"[{client_addr}] Malformed request line. Connection closed.")
        return

    # Convert headers list to dict (lowercase keys for ease)
    header_dict = {}
    for h in request_headers[1:]:
        parts = h.split(":", 1)
        if len(parts) == 2:
            k, v = parts[0].strip(), parts[1].strip()
            header_dict[k.lower()] = v

    # If no Host header is found, we might parse from the URL directly
    remote_host, remote_port, path = extract_host_port_path(url_or_path, header_dict)

    # If method != GET, we can either handle or just send an error
    # For this assignment, let's only handle GET
    if method.upper() != "GET":
        send_http_error(client_conn, 501, "Not Implemented")
        client_conn.close()
        print(f"[{client_addr}] Method {method} not supported.")
        return

    # ----------------------------------------------------------
    # Special case: If path ends with "Smiley.jpg", serve local troll image.
    # This is the simplest approach: we do not even contact the remote server.
    # (Alternatively, you could do something more advanced.)
    # ----------------------------------------------------------
    if path.lower().endswith("smiley.jpg"):
        # Serve local troll image
        serve_local_image(client_conn, http_version, TROLL_IMAGE_PATH)
        client_conn.close()
        print(f"[{client_addr}] Served troll image for Smiley.jpg request.")
        return

    # Build a new request to send to the remote server
    # We’ll go with HTTP/1.0 to keep it simpler, and close the connection.
    out_headers = []
    out_headers.append(f"{method} {path} HTTP/1.0")
    out_headers.append(f"Host: {remote_host}")
    out_headers.append("Connection: close")

    # Forward other relevant headers except any Proxy-Connection, etc.
    # We'll keep User-Agent, Accept, etc.
    for line in request_headers[1:]:
        lower = line.lower()
        if lower.startswith("proxy-connection"):
            continue
        if lower.startswith("connection"):
            continue
        out_headers.append(line)

    out_req = "\r\n".join(out_headers) + "\r\n\r\n"

    # Connect to remote server
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect((remote_host, remote_port))
    except Exception as e:
        print(f"[{client_addr}] Could not connect to {remote_host}:{remote_port} - {e}")
        send_http_error(client_conn, 502, "Bad Gateway")
        client_conn.close()
        return

    # Send the request
    server_socket.sendall(out_req.encode('utf-8'))

    # Now read the response headers
    response_headers = read_http_headers(server_socket)
    if not response_headers:
        # The server closed or sent no headers
        # We'll just close
        server_socket.close()
        client_conn.close()
        print(f"[{client_addr}] Server closed without sending headers.")
        return

    # The first line is status, e.g. "HTTP/1.1 200 OK"
    resp_status_line = response_headers[0]
    # Convert next lines to dict
    resp_header_dict = {}
    for h in response_headers[1:]:
        parts = h.split(":", 1)
        if len(parts) == 2:
            k = parts[0].strip().lower()
            v = parts[1].strip()
            resp_header_dict[k] = v

    # Check content-length or chunked
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

    # We'll reconstruct the response to send to the client
    # but might modify the body if it's text and not compressed/chunked
    out_resp_headers = []
    out_resp_headers.append(resp_status_line)

    # We might alter or remove certain headers (e.g. remove chunked if we re-generate content-length).
    # But let's keep it simple: if it's chunked or compressed, we won't attempt to do replacements,
    # we'll just forward raw.
    # So we basically forward all headers as-is, but if we do replacements, we'll recalc content-length.
    skip_headers = set(["transfer-encoding"])  # we'll handle chunked logic ourselves
    for k, v in resp_header_dict.items():
        if k in skip_headers:
            continue
        # We'll preserve this header for now
        # We'll re-add content-length later if we replace the body
        if k == "content-length":
            continue
        # Re-emit the header
        header_line = f"{k}: {v}"
        out_resp_headers.append(header_line)

    # We'll read the body now
    #  - If chunked or compressed, forward it as is (no replacements).
    #  - Else, read entire body, do text replacements, fix content-length.
    body_data = b""

    if (not is_chunked) and (content_encoding == "") and ("text" in content_type):
        # => we attempt to read the entire body, do replacements
        if content_length is not None:
            # read exactly content_length bytes
            body_data = read_exact(server_socket, content_length)
        else:
            # read until EOF
            body_data = read_until_eof(server_socket)

        # do the replacements (Smiley->Trolly, Stockholm->Linköping)
        try:
            text_str = body_data.decode('utf-8', errors='replace')
            text_str = text_str.replace("Smiley", "Trolly")
            text_str = text_str.replace("Stockholm", "Linköping")
            body_data = text_str.encode('utf-8')
        except Exception as e:
            # fallback: just keep original body if any decode error
            pass

        # Now recalc content-length
        new_len = len(body_data)
        out_resp_headers.append(f"Content-Length: {new_len}")

    else:
        # We do NOT do replacements. We just forward raw.
        # So let's keep or forward the original content-length or chunked
        # If chunked, let's forward the "Transfer-Encoding: chunked"
        if is_chunked:
            out_resp_headers.append("Transfer-Encoding: chunked")
        elif content_length is not None:
            out_resp_headers.append(f"Content-Length: {content_length}")
        # read the body and forward raw
        forward_raw_data = b""

    # Add a blank line to end headers
    out_resp_headers.append("")
    out_resp_headers_raw = "\r\n".join(out_resp_headers).encode('utf-8')

    # Send headers to client
    client_conn.sendall(out_resp_headers_raw)

    if (not is_chunked) and (content_encoding == "") and ("text" in content_type):
        # We have the modified body in memory (body_data). Send it.
        client_conn.sendall(body_data)
    else:
        # Just forward raw from server to client
        if content_length is not None:
            # forward exactly content_length
            forward_raw(server_socket, client_conn, content_length)
        else:
            # chunked or no length -> forward until EOF
            forward_raw(server_socket, client_conn, None)

    # Close sockets
    server_socket.close()
    client_conn.close()
    print(f"[{client_addr}] Done. Connection closed.")

def parse_request_line(line):
    """
    Parse the first line of an HTTP request, e.g. "GET http://example.com/ HTTP/1.1"
    Returns (method, url_or_path, http_version) or (None, None, None) if malformed.
    """
    parts = line.split()
    if len(parts) != 3:
        return None, None, None
    return parts[0], parts[1], parts[2]

def extract_host_port_path(url_or_path, header_dict):
    """
    Given something like 'http://www.example.com:8080/test/page.html'
    or '/test/page.html' plus a 'Host' header, return (host, port, path).
    Defaults port to 80 if none given.
    """
    default_port = 80
    # If the request line is a full URL: e.g. "http://hostname:port/path"
    if url_or_path.lower().startswith("http://"):
        # strip off 'http://'
        tmp = url_or_path[7:]
        # find first slash
        slash_pos = tmp.find('/')
        if slash_pos == -1:
            # no slash => no path
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
    resp = (f"HTTP/1.0 {code} {message}\r\n"
            f"Content-Type: text/html\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
            f"{body}")
    sock.sendall(resp.encode('utf-8'))

def read_exact(sock, length):
    """
    Read exactly `length` bytes from sock, or fewer if EOF.
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
    Sends a local file (image) as an HTTP response.
    If the file is not found, sends a 404.
    """
    try:
        with open(filepath, "rb") as f:
            img_data = f.read()
        # Send a 200 response
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
        # Send 404
        body = "<html><body><h2>404 Not Found</h2></body></html>"
        resp = (f"{http_version} 404 Not Found\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
                f"{body}")
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
        # Spawn a thread to handle each client
        t = threading.Thread(target=handle_client, args=(client_conn, client_addr))
        t.daemon = True  # so it won't block exit if main thread ends
        t.start()

if __name__ == "__main__":
    main()
