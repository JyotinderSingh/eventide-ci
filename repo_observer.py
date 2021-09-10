"""
Repo Observer Service to observe the repository.

Checks for new commits to the master repo, and will notify the dispatcher of
the latest commit ID, so the dispatcher can dispatch the tests against this
commit ID
"""
import time
import argparse
import os
import subprocess
import helpers
import socket


def poll():
    # parse the arguments passed to the observer.
    parser = argparse.ArgumentParser()
    parser.add_argument("--dispatcher-server",
                        help="dispatcher host:port, by default it uses"
                        "localhost:8888", default="localhost:8888",
                        action="store")

    parser.add_argument("repo", metavar="REPO", type=str,
                        help="path to the repository this will observe.")

    args = parser.parse_args()
    dispatcher_host, dispatcher_port = args.dispatcher_server.split(":")

    while True:
        try:
            # call the bash script that will update the repo and check
            # for changtes. If there's a change, it will drop a .commit_id file
            # with he latest commit in the current working directory.
            subprocess.check_output(["./update_repo.sh", args.repo])
        except subprocess.CalledProcessError as e:
            raise Exception("Could not update and check repository. " +
                            f"Reason: {e.output}")

        # When update_repo.sh finishes running, we check the existence of the
        # .commit_id file. If it exists, then we know we have a new commit, and
        # we need to notify the dispatcher so it can kick off the tests.
        response = None
        if os.path.isfile(".commit_id"):
            try:
                # We check the dispatcher server's status by sending a status request
                # to make sure there are no problems with it, and to make sure it
                # is ready for new instructions.
                reponse = helpers.communicate(
                    dispatcher_host, int(dispatcher_port), "status")
            except socket.error as e:
                raise Exception(
                    f"Could not communicate with dispatcher server: {e}")

            if response == "OK":
                commit = ""
                with open(".commit_id", "r") as f:
                    commit = f.readline()
                response = helpers.communicate(dispatcher_host, int(
                    dispatcher_port), f"dispatch:{commit}")

                if response != "OK":
                    raise Exception(f"Could not dispatch the test: {response}")

                print("dispatched!")

            else:
                raise Exception(f"Could not dispatch the test: {response}")

        time.sleep(5)


if __name__ == "__main__":
    poll()
