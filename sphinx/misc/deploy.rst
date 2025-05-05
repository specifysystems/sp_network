Deploy Specify Network
##############################

Create an EC2 instance
========================

Install Specify Network code
=======================================

Create SSL certificates
============================

`SSL certificate installation <ssl_certificates>`_.


Build/deploy Specify Network
================================

Environment status checks:
--------------------------

* Ensure the FQDN(s) in .env.*.conf and server/server_name AND SSL key location in
  nginx.conf agree for each subdomain deployment.

  .env.analyst.conf::

    FQDN=<FQDN>

  nginx.conf::

    server {
      ...
      server_name  analyst.localhost;

      ssl_certificate /etc/letsencrypt/live/<FQDN>/fullchain.pem;
      ssl_certificate_key /etc/letsencrypt/live/<FQDN>/privkey.pem;


* Ensure no webserver (i.e. apache2) is running on the host machine
* Ensure the SSL certificates are present on the host machine, and visible to the
  containers.
* Ensure that the port in the deployment command in the Dockerfile (for running
  flask in the appropriate development or production flask container) matches the
  appropriate docker-compose file.  The development and production commands point
  to different flask applications via the variables FLASK_APP and FLASK_MANAGE, defined
  in the docker compose files.  The command also indicates which port the app runs on:
  5000 for FLASK_APP on production, DEBUG_PORT for FLASK_MANAGE on development.

  Dockerfile::

        # Production flask image from base
        ...
        CMD venv/bin/python -m gunicorn -w 4 --bind 0.0.0.0:5000 ${FLASK_APP}

  docker-compose.yml::

      services:
        analyst:
          ...
          environment:
            - FLASK_APP=flask_app.analyst.routes:app
          ...
        broker:
          ...
          environment:
            - FLASK_APP=flask_app.broker.routes:app

  Dockerfile::

        # Development flask image from base
        FROM base as dev-flask
        ...
        CMD venv/bin/python -m debugpy --listen 0.0.0.0:${DEBUG_PORT} -m ${FLASK_MANAGE} run --host=0.0.0.0

  docker-compose.development.yml::

      broker:
        ...
        ports:
          - "5001:5001"
        environment:
          - FLASK_APP=flask_app.broker.routes:app
          - FLASK_MANAGE=flask_app.broker.manage
          - DEBUG_PORT=5001
        ...

      analyst:
        ...
        ports:
          - "5002:5002"
        environment:
          - FLASK_APP=flask_app.analyst.routes:app
          - FLASK_MANAGE=flask_app.analyst.manage
          - DEBUG_PORT=5002


* The proxy pass in nginx.conf points to the container
  name (http://container:port) using http (even for SSL); it points to port 5000
  for each container.  The Dockerfile command indicates which port the app runs on (5000
  for FLASK_APP on production, DEBUG_PORT for FLASK_MANAGE on development.
  (TODO: clarify this!
  https://maxtsh.medium.com/a-practical-guide-to-implementing-reverse-proxy-using-dockerized-nginx-with-multiple-apps-ad80f6dfce17):

nginx.conf::

    # Broker
    server {
      listen 443 ssl;
      location / {
        ...
        # pass queries to the broker container
        proxy_pass http://broker:5000;
      ...
    # Analyst
    server {
      listen 443 ssl;
      location / {
        # pass queries to the analyst container
        proxy_pass http://analyst:5000;

Host machine preparation
----------------------------
These tasks should be set up on the EC2 host, possibly in the userdata
script run on instantiation.

* Create a directory on the host machine to share data with docker containers.

  * /home/ubuntu/aws_data directory on the host will contain data downloaded from S3
    for data analysis outputs used by the SpecifyNetwork Analyst APIs.

    * download input data into this directory prior to volume creation in deployment
      (docker compose)

      * TODO: set up an automated task to download this on creation in S3

    * docker-compose.yml bind-mounts this host directory to the /volumes/aws_data
      directory as Read-Only on the analyst container.
    * AWS_INPUT_DATA in the .env.analyst.conf file points to this volume
    * AWS_INPUT_PATH in python code references the AWS_INPUT_DATA environment variable
      in the flask_app/analyst/base.py service
    * currently, this directory only holds the sparse matrix data, uncompressed and
      possibly the zip file. (speciesxdataset_matrix_2024_02_01.npz, .json, .zip)



Standard manipulation
=================================

Edit the docker environment files
-------------------------------------------

* Add the deployments' FQDN to the files .env.broker.conf and .env.analyst.conf and
  nginx.conf
* Change the FQDN value to the fully qualified domain name of the server.

  * If this is a local testing deployment, it will be "localhost"
  * For a development or production server it will be the FQDN with correct subdomain
    for each container, i.e FQDN=broker.spcoco.org in .env.broker.conf and
    FQDN=analyst.spcoco.org in .env.analyst.conf

Run the containers (production)
-------------------------------------------

Start the containers with the Docker composition file::

    sudo docker compose -f docker-compose.yml up -d

Specify Network is now available at [https://localhost/](https://localhost:443)`

Make sure the host machine is not running a webserver (apache2) which will bind
the http/https ports and not allow the docker containers to use them.


Run the containers (development)
-------------------------------------------

Note that the development compose file, docker-compose.development.yml, is referenced
first on the command line.  It has elements that override those defined in the
general compose file, docker-compose.yml::

    sudo docker compose -f compose.development.yml -f compose.yml  up

Flask has hot-reload enabled.


Rebuild/restart
-------------------------------------------

To delete all containers, images, networks and volumes, stop any running
containers::

    sudo docker compose stop


And run this command (which ignores running container)::

    sudo docker system prune --all --volumes

Then rebuild/restart::

    sudo docker compose up -d
    # or
    sudo docker compose -f docker-compose.development.yml -f docker-compose.yml  up

Examine container
-------------------------------------------

To examine containers at a shell prompt::

    sudo docker exec -it sp_network-nginx-1 /bin/sh

Error port in use:
"Error starting userland proxy: listen tcp4 0.0.0.0:443: bind: address already in use"

See what else is using the port.  In my case apache was started on reboot.  Bring down
all docker containers, shut down httpd, bring up docker.

::
    lsof -i -P -n | grep 443
    sudo docker compose down
    sudo systemctl stop httpd
    sudo docker compose  up -d

Run Docker on OSX
=================================

Need to bind server to 0.0.0.0 instead of 127.0.0.1

Test by getting internal IP, using ifconfig, then command to see if connects successfully::

    nc -v x.x.x.x 443

Then can use same IP in browser, i.e. https://x.x.x.x/api/v1/name/
This only exposes the broker, not the analyst services.



Troubleshooting
=================================

Out of Space Problem
------------------

Running `certbot certificates` failed because the EC2 instance running Docker
containers for Specify Network development shows disk full::

    root@ip-172-31-86-62:~# df -h
    Filesystem      Size  Used Avail Use% Mounted on
    /dev/root       7.6G  7.6G     0 100% /
    tmpfs           483M     0  483M   0% /dev/shm
    tmpfs           194M   21M  173M  11% /run
    tmpfs           5.0M     0  5.0M   0% /run/lock
    /dev/xvda15     105M  6.1M   99M   6% /boot/efi
    overlay         7.6G  7.6G     0 100% /var/lib/docker/overlay2/82d82cc5eb13260207b94443934c7318af651ea96a5fcd88c579f23224ba099d/merged
    overlay         7.6G  7.6G     0 100% /var/lib/docker/overlay2/cb0d78289131b3925e21d7eff2d03c79fe432eeba2d69a33c6134db40dc3caf3/merged
    overlay         7.6G  7.6G     0 100% /var/lib/docker/overlay2/3bd6d12b36e746f9c74227b6ac9d928a3179d8b604a9dea4fd88625eab84be1f/merged
    tmpfs            97M  4.0K   97M   1% /run/user/1000

The disk is small, but the culprit is /var/lib/docker/overlay2

Some strategies at:
https://forums.docker.com/t/some-way-to-clean-up-identify-contents-of-var-lib-docker-overlay/30604/19

Solution:
...........

* The instance was created with a volume of an 8gb default size.
* Stop the instance
* Modify the volume.
* Restart the EC2 instance - ok while the volume is in the optimizing state.
* If the instance does not recognize the extended volume immediately::

    ubuntu@ip-172-31-91-57:~$ df -h
    Filesystem      Size  Used Avail Use% Mounted on
    /dev/root       7.6G  7.6G     0 100% /
    tmpfs           475M     0  475M   0% /dev/shm
    tmpfs           190M   11M  180M   6% /run
    tmpfs           5.0M     0  5.0M   0% /run/lock
    /dev/xvda15     105M  6.1M   99M   6% /boot/efi
    tmpfs            95M  4.0K   95M   1% /run/user/1000
    ubuntu@ip-172-31-91-57:~$ sudo lsblk
    sudo: unable to resolve host ip-172-31-91-57: Temporary failure in name resolution
    NAME     MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
    loop0      7:0    0 24.9M  1 loop /snap/amazon-ssm-agent/7628
    loop1      7:1    0 25.2M  1 loop /snap/amazon-ssm-agent/7983
    loop2      7:2    0 55.7M  1 loop /snap/core18/2796
    loop3      7:3    0 55.7M  1 loop /snap/core18/2812
    loop4      7:4    0 63.9M  1 loop /snap/core20/2105
    loop5      7:5    0 63.9M  1 loop /snap/core20/2182
    loop6      7:6    0   87M  1 loop /snap/lxd/27037
    loop7      7:7    0   87M  1 loop /snap/lxd/27428
    loop8      7:8    0 40.4M  1 loop /snap/snapd/20671
    loop9      7:9    0 39.1M  1 loop /snap/snapd/21184
    xvda     202:0    0   30G  0 disk
    ├─xvda1  202:1    0  7.9G  0 part /
    ├─xvda14 202:14   0    4M  0 part
    └─xvda15 202:15   0  106M  0 part /boot/efi

* extend the filesystem:
  https://docs.aws.amazon.com/ebs/latest/userguide/recognize-expanded-volume-linux.html
* In this case we want to extend xvda1, so::

    $ sudo growpart /dev/xvda 1
    sudo: unable to resolve host ip-172-31-91-57: Temporary failure in name resolution
    mkdir: cannot create directory ‘/tmp/growpart.1496’: No space left on device
    FAILED: failed to make temp dir

* We must free up space to allow extension::

    $ sudo docker system prune --all --volumes
    sudo: unable to resolve host ip-172-31-91-57: Temporary failure in name resolution
    WARNING! This will remove:
      - all stopped containers
      - all networks not used by at least one container
      - all volumes not used by at least one container
      - all images without at least one container associated to them
      - all build cache

    Are you sure you want to continue? [y/N] y
    Deleted Containers:
    24768ca767d37f248eff173f13556007468330298329200d533dfa9ca011e409
    809709d6f8bfa8575009a0d07df16ee78852e9ab3735aa19561ac0dbc0313123
    64591ed14ecae60721ea367af650683f738636167162f6ed577063582c210aa9

    Deleted Networks:
    sp_network_nginx

    Deleted Images:
    untagged: nginx:alpine
    untagged: nginx@sha256:a59278fd22a9d411121e190b8cec8aa57b306aa3332459197777583beb728f59
    deleted: sha256:529b5644c430c06553d2e8082c6713fe19a4169c9dc2369cbb960081f52924ff
    ...
    deleted: sha256:e74dab46dbca98b4be75dfbda3608cd857914b750ecd251c4f1bdbb4ef623c8c

    Total reclaimed space: 1.536GB

* Extend filesystem::

    $ sudo growpart /dev/xvda 1
    sudo: unable to resolve host ip-172-31-91-57: Temporary failure in name resolution
    CHANGED: partition=1 start=227328 old: size=16549855 end=16777183 new: size=62687199 end=62914527
    $ df -h
    Filesystem      Size  Used Avail Use% Mounted on
    /dev/root       7.6G  5.7G  2.0G  75% /
    tmpfs           475M     0  475M   0% /dev/shm
    tmpfs           190M   18M  173M  10% /run
    tmpfs           5.0M     0  5.0M   0% /run/lock
    /dev/xvda15     105M  6.1M   99M   6% /boot/efi
    tmpfs            95M  4.0K   95M   1% /run/user/1000


* Stop apache2 if running
* Rebuild the docker containers

Problem: Failed programming external connectivity
--------------------------------------------------------

[+] Running 6/5
 ✔ Network sp_network_default        Created                                                                                                                                                          0.1s
 ✔ Network sp_network_nginx          Created                                                                                                                                                          0.1s
 ✔ Container sp_network-front-end-1  Created                                                                                                                                                          0.2s
 ✔ Container sp_network-broker-1     Created                                                                                                                                                          0.2s
 ✔ Container sp_network-analyst-1    Created                                                                                                                                                          0.2s
 ✔ Container sp_network-nginx-1      Created                                                                                                                                                          0.1s
Attaching to analyst-1, broker-1, front-end-1, nginx-1
Error response from daemon: driver failed programming external connectivity on endpoint
sp_network-nginx-1 (1feeaa264a757ddf815a34db5dd541f48d3f57aa21ef104e3d5823efbb35f9ab):
Error starting userland proxy: listen tcp4 0.0.0.0:80: bind: address already in use

Solution
...............

Stop apache2 on the host machine


Problem: Permission denied for downloading/accessing S3 data
---------------------------------------

For now, we are using a local configuration file in the home directory with
aws_access_key_id and aws_secret_access_key.

Configuration Solution (fail)
......................

Create an .aws directory in the user directory, and create the files
credentials and config.  In the credentials file, put the
permitted user's access key and secret access key::

    [default]
    aws_access_key_id = <access_key>
    aws_secret_access_key = <secret key>

The config file should contain::

    [default]
    region = us-east-1
    output = json

This works for the host EC2 instance, but still getting ClientError Forbidden in
analyst code on container.

IAM Role Solution (fail)
.....................

Create an IAM role for S3 access, attach it to the EC2 instance, then verify:
https://repost.aws/knowledge-center/ec2-instance-access-s3-bucket

This works for the host EC2 instance, but still getting ClientError Forbidden in
analyst code on container.

Bind-mount solution (success!)
.....................

Using the aws cli and the command::

 aws s3 cp s3://specnet-us-east-1/summary/speciesxdataset_matrix_2024_02_01.zip /tmp/

The EC2 instance successfully used the Configuration Solution (~/.aws/credentials)
above to download files from S3.

However, when using only the IAM Role Solution, with the EC2 instance having a role
full access to the specnet-us-east-1 bucket, the EC2 instance got::

  "fatal error: An error occurred (403) when calling the HeadObject operation: Forbidden"


Chose to download the data to the EC2 instance, and bind-mount that directory to the
container.

TODO: In the future, this should be done as soon as new data from GBIF has
been processed at the first of the month.  The API will query for the data named with
the date as the first of the current month (aka, on July 2, 2024, search for
<datatype>_2024-07-01.<ext>)

General debug messages for the flask container
----------------------------------------------

* Print logs::

  sudo docker logs sp_network-nginx-1 --tail 100

Problem: Only broker endpoints are active
--------------------------------------------

Specify network uses 2 flask apps, broker and analyst, each with their own subdomain.
The Docker file and docker-compose files must be configured for the correct flask app
to send API requests from a subdomain to the appropriate docker container.

Solution:
..................

Make sure that the following 3 files have the correct FQDN values in them:

  * .env.analyst.conf: contains the analyst FQDN (i.e. FQDN=analyst(-dev).<domain>)
  * .env.broker.conf: contains the broker FQDN (i.e. FQDN=broker(-dev).<domain>)
  * config/nginx.conf: contains the server_name and proxy_pass (to container) for each
    flask app.::

    # Broker
    server {
      listen 443 ssl;
      index index.html;
      server_name  broker-dev.<domain>;
      location / {
        ...
        # pass queries to the broker container
        proxy_pass http://broker:5000;
      ...
    # Analyst
    server {
      listen 443 ssl;
      index index.html;
      server_name  analyst-dev.<domain>;
      location / {
        # pass queries to the analyst container
        proxy_pass http://analyst:5000;
