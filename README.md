# Divvy Python Client

A client for the [Divvy rate limit server](https://github.com/button/divvy).
Includes support for Twisted, if that's your jam.

1. [Requirements](#requirements)
2. [Usage](#usage)
3. [Other Features](#other-features)
4. [License and Copyright](#license-and-copyright)


## Requirements

* Python version 2.7 or newer.
* If using Twisted, you'll need the `Twisted` and `txconnpool` packages.


## Usage

Procedural client example:

```python
from divvy import DivvyClient

client = DivvyClient("localhost", 8321)
resp = client.hit(method="GET", path="/pantry/cookies")
if resp.is_allowed:
	print("Request is within the rate limit: {}".format(resp))
else:
	print("Request exceeds the rate limit: {}".format(resp))
```

For the Twisted client, there's a single-connection example in [twisted_poc.py](twisted_poc.py), and a connection pooling example in [twisted_pool_poc.py](twisted_pool_poc.py).


## Building and testing

```bash
pip install requirements.txt  # only needed in the build/test phase
find . -name "*.py" | xargs pycodestyle
pylint -E *.py divvy tests
python -m unittest discover tests/
```


## Other Features

### Benchmarking

Benchmark the client -- and your Divvy server -- with the included `benchmark.py`. Run with `-h` for comprehensive help.


## License and Copyright

Licensed under the MIT license. See `LICENSE.txt` for full terms.

Copyright 2018 Foxpass, Inc.
