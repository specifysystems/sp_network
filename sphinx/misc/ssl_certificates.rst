Specify Network SSL certificates
######################################


SSL certificates are served from the host machine, and are administered by
Letsencrypt using Certbot.  They are only valid for 90 days at a time.

TODO: move administration to AWS, and script renewal if necessary

TLS/SSL using Certificate Authority (CA)
..................................................

* Make sure that DNS has propogated for domain for SSL
* Stop apache service
* request a certificate for the domain

::

    $ sudo systemctl stop apache2
    $ sudo certbot certonly -v
    Saving debug log to /var/log/letsencrypt/letsencrypt.log

    How would you like to authenticate with the ACME CA?
    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    1: Spin up a temporary webserver (standalone)
    2: Place files in webroot directory (webroot)
    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    Select the appropriate number [1-2] then [enter] (press 'c' to cancel): 1
    Plugins selected: Authenticator standalone, Installer None
    Enter email address (used for urgent renewal and security notices)
     (Enter 'c' to cancel): aimee.stewart@ku.edu

    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    Please read the Terms of Service at
    https://letsencrypt.org/documents/LE-SA-v1.3-September-21-2022.pdf. You must
    agree in order to register with the ACME server. Do you agree?
    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    (Y)es/(N)o: Y

    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    Would you be willing, once your first certificate is successfully issued, to
    share your email address with the Electronic Frontier Foundation, a founding
    partner of the Let's Encrypt project and the non-profit organization that
    develops Certbot? We'd like to send you email about our work encrypting the web,
    EFF news, campaigns, and ways to support digital freedom.
    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    (Y)es/(N)o: N
    Account registered.
    Please enter the domain name(s) you would like on your certificate (comma and/or
    space separated) (Enter 'c' to cancel): dev.spcoco.org, analyst-dev.spcoco.org, broker-dev.spcoco.org
    Requesting a certificate for dev.spcoco.org and 2 more domains
    Performing the following challenges:
    http-01 challenge for analyst-dev.spcoco.org
    http-01 challenge for broker-dev.spcoco.org
    http-01 challenge for dev.spcoco.org
    Waiting for verification...
    Cleaning up challenges

    Successfully received certificate.
    Certificate is saved at: /etc/letsencrypt/live/dev.spcoco.org/fullchain.pem
    Key is saved at:         /etc/letsencrypt/live/dev.spcoco.org/privkey.pem
    This certificate expires on 2024-06-19.
    These files will be updated when the certificate renews.
    Certbot has set up a scheduled task to automatically renew this certificate in the background.

    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    If you like Certbot, please consider supporting our work by:
     * Donating to ISRG / Let's Encrypt:   https://letsencrypt.org/donate
     * Donating to EFF:                    https://eff.org/donate-le
    - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


Bind-mount the letsencrypt directory
-------------------------------------------------------

* For all containers responding to web requests, bind-mount the /etc/letsencrypt
  directory (or the directory containing self-signed certificates) from the host machine
  to the container

::

   version: "3.9"
   services:
     ...
     nginx:
       ...
       volumes:
         - "/etc/letsencrypt:/etc/letsencrypt:ro"

Renew Certbot SSL certificates
.........................................

SSL certificates are served from the instance (AWS EC2), and need port 80 to be renewed.
These are administered by Letsencrypt using Certbot and are only valid for 90 days at
a time. When it is time for a renewal (approx every 60 days), bring the docker
containers down.  Renew the certificates, then bring the containers up.

TODO: is rebuild necessary since using bind mount?? i.e. Prune the volumes so the new
containers will be created with the updated certificates.

Amazon EC2 containers do not need apache running, certbot runs its own temp web server.

Test with https://broker.spcoco.org/api/v1/frontend/?occid=01493b05-4310-4f28-9d81-ad20860311f3

::

    $ sudo certbot certificates
    $ sudo docker compose stop
    $ sudo certbot renew
    $ sudo docker compose up -d

Local self-signed certificates
.........................................
To run the containers, generate `fullchain.pem` and `privkey.pem` (certificate
and the private key) using Let's Encrypt and link these files in `./sp_network/config/`.

While in development, generate self-signed certificates then link them in
~/git/sp_network/config/ directory for this project::

  $ mkdir ~/certificates

  openssl req \
  -x509 -sha256 -nodes -newkey rsa:2048 -days 365 \
  -keyout ~/certificates/privkey.pem \
  -out ~/certificates/fullchain.pem

  $ cd ~/git/sp_network/config
  $ ln -s ~/certificates/privkey.pem
  $ ln -s ~/certificates/fullchain.pem

To run either the production or the development containers with HTTPS
support, generate `fullchain.pem` and `privkey.pem` (certificate and the private
key) using Let's Encrypt, link these files in the `./config/` directory.
Full instructions in the docs/aws-steps.rst page, under `Set up TLS/SSL`

Modify the `FQDN` environment variable in `.env.conf` as needed.


TODO: Autorenew SSL with Certbot/LetsEncrypt
.........................................
https://medium.com/swlh/dockerizing-two-web-servers-to-respond-to-the-same-domain-eb9c15734a68


TODO: SSL through Amazon
.........................................

* Create Elastic IP address for EC2 instance
* Request a public certificate through Certificate Manager (ACM)
  * Choose DNS validation
  * Add tags sp_network, dev or prod, others
