"""Static dev server for the visualization, with HTTP range support.

PMTiles reads small byte ranges out of the archive, and Python's stock
http.server ignores the Range header and returns the whole file with status 200.
That makes a 15 MB archive unusable locally even though it works in production,
where raw.githubusercontent.com does honour ranges.

    uv run python viz/serve.py        # then open http://127.0.0.1:8765
"""

import argparse
import functools
import http.server
import os
import re
import socketserver
from pathlib import Path

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        header = self.headers.get("Range")
        if not header:
            return super().send_head()

        match = RANGE_RE.fullmatch(header.strip())
        if not match:
            self.send_error(400, "malformed Range header")
            return None

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        size = os.fstat(f.fileno()).st_size
        first, last = match.group(1), match.group(2)

        if first:
            start = int(first)
            end = int(last) if last else size - 1
        else:
            # suffix range: bytes=-N means the last N bytes
            if not last:
                f.close()
                self.send_error(400, "malformed Range header")
                return None
            start = max(0, size - int(last))
            end = size - 1

        if start >= size:
            f.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        end = min(end, size - 1)
        length = end - start + 1

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        f.seek(start)
        self.wfile.write(f.read(length))
        f.close()
        return None

    def log_message(self, fmt, *args):
        if "code 4" in (fmt % args) or "code 5" in (fmt % args):
            super().log_message(fmt, *args)


class DevServer(socketserver.ThreadingTCPServer):
    # Without this a restart fails while the previous socket sits in TIME_WAIT.
    allow_reuse_address = True
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--root", default=str(Path(__file__).parent))
    args = parser.parse_args()

    handler = functools.partial(RangeRequestHandler, directory=args.root)
    with DevServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {args.root} at http://127.0.0.1:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
