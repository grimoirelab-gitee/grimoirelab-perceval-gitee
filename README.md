# perceval-gitee

Bundle of Perceval backends for Gitee.

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
$ git clone https://github.com/grimoirelab-gitee/grimoirelab-perceval-gitee.git
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
$ perceval gitee https://gitee.com/willemjiang/gitee-example --from-date 2020-03-01 --to-date 2020-05-02
```

## License

Licensed under GNU General Public License (GPL), version 3 or later.
