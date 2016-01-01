Clementine AWS Lambdas
======================

This directory contains code intended to run as an
[AWS Lambda](https://aws.amazon.com/documentation/lambda/).

### Running Locally
```shell
gradle build shadowJar
java -jar ./build/libs/lambda.clementine-player.org-all.jar
```

### Running on AWS
```shell
gradle build buildZip
```

Upload `build/distributions/lambda.clementine-player.org.zip` to the console.
