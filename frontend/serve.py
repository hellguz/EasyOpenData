import http.server
import socketserver

PORT = 8080

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Set the correct MIME type for JS/TSX files
        if self.path.endswith('.js'):
            self.send_header("Content-Type", "application/javascript")
        elif self.path.endswith('.tsx'):
            self.send_header("Content-Type", "application/javascript")  # TypeScript gets compiled to JS
        return super().end_headers()

with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
    print(f"Serving at http://localhost:{PORT}")
    httpd.serve_forever()
