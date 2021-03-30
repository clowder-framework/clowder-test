# clowder-test


## Setup test_extraction_data.yml

rename `test_extraction_data.yml.template` to `test_extraction_data.yml`.

You can add extractions test_extraction_data.yml files. If you know of a test that will fail you can add a skip there with a description of why that test is skipped.


## Setup and Run 

- Create the Clowder test Docker image and run the Docker container:

```
docker build -t clowder-test.pytest .
```

```
docker run clowder-test.pytest
```

- Create the Clowder test web GUI Docker image and run the Docker container:
```
cd web/
```
```
docker build -t clowder-test.web .
```
```
docker run -p 8008:80 --rm -e "HOST=youhostip" clowder-test.web
```