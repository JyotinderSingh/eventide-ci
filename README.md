# 🌘 Eventide 

### Eventide is a simple distributed Continuous Integration system.

This is an **initial prototype** for a distributed Continuous Integration System.

---

## Features

- Distributed architecture for scalability - supports virtually unlimited concurrent test runners.
- New test runners auto register themselves with the cluster.
- Test results get stored in a file with a summary of the test runs.
- Includes heartbeat mechanism among different services, which allows for some simple error handling:
  - If a test runner dies, the dispatcher service will automatically figure this out and remove it from the pool - and will give another runner (if available) the job. Otherwise, it will wait for the current test runners to finish processing or a new test runner to register itself in the pool.
  - If the dispatcher service dies, the test runners and repo observer service will notice this and gracefully shut down.

## Architecture

The system is built of 3 main components:

- **Observer Service**: This service monitors a git repository for new changes - when a commit is detected it notifies the dispatcher service about the same.
- **Dispatcher Service**: Responsible for distributing incoming jobs (commit IDs against which we need to run a test) to available test runners. Also reponsible for registering new test runners that try to register themselves with the cluster. In case a runner crashes, the dispatcher service removes it from the registry. In case a test runner fails while running a test, the test a re-assigned to another healthy node.
- **Test Runner Service**: Responsible for actually executing the tests on the given commit IDs. Ideally has a large number of nodes to allow several concurrent test runs.

## Steps to run

### Setup

Create a repository you want Eventide to monitor. Currently Eventide supports git repositories only.

This is the main repository where the developers will check in their code.

```
mkdir test_repo
cd test_repo
git init
```

To get started, we need at least one commit in this master repository. You can add the [example tests provided here](./tests) for testing purposes.

You would want your tests to be present in a directory called `tests`. This is where Eventide looks for test files to be run.

```
cp -r /this/directory/tests/ /path/to/test_repo/
cd /path/to/test_repo
git add tests/
git commit -m "add tests"
```

The Repo Observer service will need its own copy of the repository, since it might exist on a different system altogether.
Let's create a clone of the master repo

```
git clone /path/to/test_repo test_repo_clone_observer
```

Similarly, the Test Runner service will also need its own copy of the repo

```
git clone /path/to/test_repo test_repo_clone_runner
```

### Running the CI

We will be using three different terminal shells to run this distributed system. You can run these on different machines as well - however you will need to provide additional arguments for the host and port numbers to the scripts.

We start the dispatcher service first, it listens for dispatch commands from the Observer service and launches tests on the Test Runner service.

```
python dispatcher_srv.py
```

In a new shell we start the Test Runner service - which authomatically registers itself with the dispatcher. You can start as many test runners as you'd like. Multiple test runners will provide better concurrent performance.

```
python test_runner_srv.py <path/to/test_repo_clone_runner>
```

The test runner will assign itself its own port in the range 8900-9000

Finally, we start the Repo Observer service.

```
python repo_observer_srv.py --dispatcher-server=localhost:8888 <path/to/test_repo_clone_observer>
```

Now Eventide is ready to run some tests!

### Launching an automated test

To launch a new run, we need to make a new commit.

Go to the master repository, and make an arbitrary change:

```
cd /path/to/test_repo
touch new_file
git add new_file
git commit -m "new file"
```

The `repo_observer_srv.py` will realize there is a new commit and notify the dispatcher service. You will be able to see the output in their respective shells and monitor the progress.

Once the dispatcher receives the results, it stores them in a `test_results/` folder in the code base, using the `commit ID` as the filename.

## Configuring the services

You can add the following command line arguments when launching the services.

### Repo Observer Service

- `--dispatcher-server`

  Dispatcher `host:port`, by default it uses `localhost:8888`

- `repo`

  path to the repository to be observed (needs a specific clone for itself)

### Dispatcher Service

- `--host`

  Dispatcher service's host, by default it uses `localhost`

- `--port`

  Port on which the service will listen, by default it uses `8888`

### Test Runner Service

- `--host`

  Host for the test runner instance, by default it uses `localhost`

- `--port`

  Port on which the test runner will listen, by default it uses values >= `8900`

- `--dispatcher-server`

  Dispatcher Service's `host:port`, by default it uses `localhost:8888`

- `repo`

  Path to the repository this will observe.

## Limitations

This software is currently under development, and has a few limitations:

- Only local git repositories are supported as of now.
- The test runner only checks the `tests/` directory in the codebase to look for tests to run. This is currently not configurable.
- Eventide checks for changes to the repo every 5 seconds. It does not test every commit made in these 5 seconds, only the most recent commit.
- The test results are stored on the file system local to the Dispatcher service. A better approach would be to send this to another service that hosts these results on the web for easier access.

## Development in progess

The current architecture is an initial proof of concept.

The final product expects to use a robust event queue for dispatching events among services, and support high availablity of the services - along with easier configuration management. We would also want to support more robust hook based workflows to detect changes in the codebase.
