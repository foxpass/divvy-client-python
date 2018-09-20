# Divvy Python Client

A client for the [Divvy rate limit server](https://github.com/button/divvy).
Includes support for Twisted, if that's your jam.

1. [Requirements](#requirements)
2. [Usage](#usage)
3. [Other Features](#other-features)
4. [License and Copyright](#license-and-copyright)


## Requirements

* Procedural client: Python version 2.7 or newer.
* Twisted client: Python version 2.7 (does not support Python 3) and the `Twisted` package.


## Usage

Procedural client example:

```python
from divvy import DivvyClient

client = DivvyClient("localhost", 8321)
resp = client.check_rate_limit(method="GET", path="/pantry/cookies")
if resp.is_allowed:
	print("Request is within the rate limit: {}".format(resp))
else:
	print("Request exceeds the rate limit: {}".format(resp))
```


Twisted client example:

```python
from divvy.twisted import DivvyClient


def handle_divvy_response(resp):
	if resp.is_allowed:
		print("Request is within the rate limit: {}".format(resp))
	else:
		print("Request exceeds the rate limit: {}".format(resp))

client = DivvyClient("localhost", 8321)
d = client.check_rate_limit(method="GET", path="/pantry/cookies")
d.addCallback(handle_divvy_response)
```


## Building and testing

```bash
pip install requirements.txt  # only needed in the build/test phase
find . -name "*.py" | xargs pycodestyle
pylint -E *.py divvy tests
python -m unittest discover tests/
```


## Other Features

### Benchmarking

Benchmark the client -- and your Divvy server -- with the included `benchmark.py`. Run with `-h` for comprehensive help. You don't need any special Divvy configuration to run the benchmark, but if you want to simulate a real environment, add this stanza to Divvy's `config.ini`:

```
[type=benchmark ip=*]
creditLimit = 5
resetSeconds = 60
actorField = ip
comment = 'for benchmark.py, 5 requests per minute, by IP'
```


## License and Copyright

Licensed under the MIT license. See `LICENSE.txt` for full terms.

Copyright 2018 Foxpass, Inc.
