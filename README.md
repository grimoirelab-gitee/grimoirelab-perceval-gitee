# perceval-gitee

Perceval backend for Gitee.(For the complete solution of grimoirelab-gitee, you can refer to the [wiki page](https://github.com/grimoirelab-gitee/grimoirelab/wiki/How-to-run-grimoirelab-gitee%3F).)


## Backends

The backends currently managed by this package support the next repositories:

* Functest

## Requirements

* Python >= 3.4
* python3-requests >= 2.7
* grimoirelab-toolkit >= 0.1.9
* perceval >= 0.12.12

## Installation

To install this package you will need to clone the repository first:

```
$ git clone https://github.com/chaoss/grimoirelab-perceval-gitee.git
```

Then you can execute the following commands:
```
$ pip3 install -r requirements.txt
$ pip3 install -e .
```

In case you are a developer, you should execute the following commands to install Perceval in your working directory (option `-e`) and the packages of requirements_tests.txt.
```
$ pip3 install -r requirements.txt
$ pip3 install -r requirements_test.txt
$ pip3 install -e .
```

## Examples

### Gitee

```
$ perceval gitee openeuler docs --from-date 2020-01-01 --to-date 2020-05-01
```

## License

Licensed under GNU General Public License (GPL), version 3 or later.
