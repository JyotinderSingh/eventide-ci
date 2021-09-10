"""
Test Dispatcher Service.

Dispatches tests against any registered test runners when the Repo Observer Service
sends it a 'dispatch' message with the commit ID to be tested. Stores the results 
when the test runners have completed running the tests and send back the results
in a 'results' message.

The service can register as many test runners as available. To register a test
runner, start the dispatcher service - then start the test runner.
"""
import re
import argparse
import time
import threading
import socket
import helpers
import socketserver
import os


# shared dispatcher code
def dispatch_tests(server, commit_id):
    """
    This function is used to find an available test runner from a pool of registered
    runners. If one is available, it will send a runtest message to it with the 
    commit ID. If none are currently available, it will wait two seconds and repeat
    this process. Once dispatched, it logs which commit ID is being tested by which
    runner in the dispatched_commits variable. If the commit ID is the pending_commits
    variable, we remove it since it has been successfully re-dispatched.
    """
    # We probably wanna stop this at one point after a fixed number of retries
    while True:
        print(f"trying to dispatch commit {commit_id[:8]} to runners")
        for runner in server.runners:
            response = helpers.communicate(runner["host"], int(
                runner["port"]), f"runtest:{commit_id}")
            if response == "OK":
                print(f"adding id {commit_id}")
                server.dispatched_commits[commit_id] = runner
                if commit_id in server.pending_commits:
                    server.pending_commits.remove(commit_id)
                return
        time.sleep(2)


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    runners = []  # Keeps track of the test runner pool.
    dead = False  # Indicate to other threads that we are no longer running.
    dispatched_commits = {}  # Keeps track of commits we dispatched.
    pending_commits = []  # Keeps track of commits we have yet to dispatch.


class DispatcherHandler(socketserver.BaseRequestHandler):
    """
    This is the RequestHandler class for our dispatcher service.
    This will dispatch test runners against the incoming commit
    and handle their requests and test results.
    """
    command_re = re.compile(r"(\w+)(:.+)*")
    BUF_SIZE = 1024

    def handle(self) -> None:
        self.data = self.request.recv(self.BUF_SIZE).strip()
        command_groups = self.command_re.match(self.data)

        if not command_groups:
            self.request.sendall("Invalid command.")
            return

        command = command_groups(1)

        if command == "status":
            # fetch status of the dispatcher
            print("in status")
            self.request.sendall("OK")

        elif command == "register":
            # Add this test runner to our pool
            print("register")
            address = command_groups.group(2)
            host, port = re.findall(r":(\w*)", address)
            runner = {"host": host, "port": port}
            self.server.runners.append(runner)
            self.request.sendall("OK")

        elif command == "dispatch":
            # Used by the repo observer to dispatch a test runner against a commit
            print("going to dispatch")
            commit_id = command_groups.group(2)[1:]
            if not self.server.runners:
                self.request.sendall("No test runners are registered.")
            else:
                # The coordinator can trust us to dispatch the test
                self.request.sendall("OK")
                dispatch_tests(self.server, commit_id)

        elif command == "results":
            # Used by test runner to report the results of a finished test run
            # format:
            # results:<commit ID>:<length of results data in bytes>:<results>
            print("got test results")
            results = command_groups(2)[1:]
            results = results.split(":")
            commit_id = results[0]
            length_msg = int(results[1])
            # 3 is the number of ":" in the send command
            remaining_buffer = self.BUF_SIZE - \
                (len(command) + len(commit_id) + len(results[1]) + 3)
            if length_msg > remaining_buffer:
                self.data += self.request.recv(length_msg -
                                               remaining_buffer).strip()
            del self.server.dispatched_commits[commit_id]
            if not os.path.exists("test_results"):
                os.makedirs("test_results")
            with open(f"test_results/{commit_id}", "W") as f:
                data = self.data.split(":")[3:]
                data = "\n".join(data)
                f.write(data)
            self.request.sendall("OK")


def serve():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host", help="dispatcher's host, by default it uses localhost",
        default="localhost",
        action="store")
    parser.add_argument(
        "--port", help="dispatcher's port, by default it uses 8888", default=888,
        action="store")
    args = parser.parse_args()

    # create the server
    server = ThreadingTCPServer((args.host, int(args.port)), DispatcherHandler)
    print(f"serving on {args.host}:{int(args.port)}")

    def runner_checker(server):
        """
        This function periodically pings each registered test runner to make sure 
        they are still reponsive. If they become unresponsive, then that runner 
        will be removed from the pool and its commit ID will be dispatched to the 
        next available runner. The function will log the commit ID in the 
        pending_commits variable.
        """
        def manage_commit_lists(runner):
            for commit, assigned_runner in server.dispatched_commits.iteritems():
                if assigned_runner == runner:
                    del server.dispatched_commits[commit]
                    server.pending_commits.append(commit)
                    break
            server.runners.remove(runner)

        while not server.dead:
            time.sleep(1)
            # ping each test runner to see if it's alive
            for runner in server.runners:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    response = helpers.communicate(
                        runner["host"], int(runner["port"]), "ping")

                    if response != "pong":
                        print(f"removing runner {runner}")
                        manage_commit_lists(runner)
                except socket.error as e:
                    manage_commit_lists(runner)

    def redistribute(server):
        """
        This function is used to dispatch the commit IDs logged in pending_commits.
        When this function runs, it checks if there are any commits in pending_commits.
        If so, it calls dispatch_tests function with the commit ID.
        """
        while not server.dead:
            for commit in server.pending_commits:
                print("redistributing pending commits")
                print(server.pending_commits)
                dispatch_tests(server, commit)
                time.sleep(5)

    runner_heartbeat = threading.Thread(target=runner_checker, args=(server,))
    redistributor = threading.Thread(target=redistribute, args=(server,))
    try:
        runner_heartbeat.start()
        redistributor.start()
        # Activate the server; this will keep running until a SIGTERM
        # interrupt is sent sent to the program using cmd+c or ctrl+c
        server.serve_forever()
    except (KeyboardInterrupt, Exception):
        # if any exception occurs, kill the thread
        server.dead = True
        runner_heartbeat.join()
        redistributor.join()


if __name__ == "__main__":
    serve()
