Overview
############################

**TODO**: update this document

Specify Network Broker services
---------------------------------

* map: <server>/api/v1/map::
  TODO: return metadata, url endpoints, and layernames for predicted species
  distributions and occurrence points

* name: <server>/api/v1/name::
  return metadata for taxonomic information on a string

* occ: <server>/api/v1/occ::
  return metadata for species occurrence points for a GUID, or for a GBIF dataset GUID

* resolve: <server>/api/v1/resolve::
  OBSOLETE: return unique identifier metadata including a direct URL for a data object.

Code resources
--------------------

* The core APIs are defined in the directory: flask_app/broker .
  There are currently 3 files (categories) that organize them:
  badge, name, occ.  TODO: add map and heartbeat.

* The classes in these files all inherit from BrokerOutput in the
  flask_app/broker/common/s2n_type.py file,
  which implements some methods to ensure they all behave consistently and use a
  subset of the same parameters and defaults.

* The flask_app/broker/base.py file contains the flask definitions and configuration to
  expose the services.

* In the flask_app/broker/common/constants.py file are constants that are used in
  multiple places.

  * **TST_VALUES** contains names and guids that can be used for testing
    services, some will return data, some will not, but none should return
    errors.

  * **APIService** contains the URL service endpoints for the different
    categories of services.

  * **ServiceProvider** contains the name, and service categories
    available for that provider.

  * All service endpoints (following the server url) will start the
    root (/api/v1), then category.  The "tentacles" service that queries all
    available providers for that category will be at that endpoint
    (example: /api/v1/name).

  * All service endpoints accept a query parameter "provider" for the providers
    available for that service, listed in ServiceProvider class.  The values may be one
    or more of the following: gbif, idb, itis, mopho, worms.