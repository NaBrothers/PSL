import sys
import threading

sys.path.insert(0, "bot/src/plugins/psl")

from utils.replay_server import start_replay_server


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = start_replay_server(port)
    if server is None:
        return
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
