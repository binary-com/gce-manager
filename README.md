# Google Compute Engine Manager

This project manages a pool of GCE (preemptible and non-preemptible) instances with desired minimum count of instances running at a time. Whenever any preemptible instances get terminated, it will attempt to restart or recreate them in different zone and if preemptible instances are unavailable, non-preemptible instances will be created instead.

There are 3 strategies used in GCE Manager to maintain compute capacity:
  1. Recycling instance - Start back the same instance if it gets terminated for the first time or an instance reaches maturity stage
  2. Relocating instance - Move instances that were terminated twice to different zones based on termination rate score
  3. Using non-preemptibles - When too many zones are high in demand, use guaranteed uptime instance for stability until demand cools down


## Instructions
1. Install Google API Python client and PyYAML via pip:
```pip install google-api-python-client pyyaml```

2. Save necessary credentials and project information as config.yml based on config-example.yml

3. Visit https://developers.google.com/identity/protocols/application-default-credentials and obtain the API credential in JSON file then save to a secure location and set GCE_GOOGLE_APPLICATION_CREDENTIALS with the path of the file in config.yml

4. To start, run ```python gce_manager.py <path_to_config_file.yml>```

5. Google Compute Engine API default rate limit is (20 requests/second) per project. GCE Manager uses (number of zones + 1) request per second to check for all instances status. If you have configured many zones in GCE_ZONE_LIST, you will need to request for a higher rate limit in order for GCE Manager work properly. For more info, visit https://cloud.google.com/compute/docs/api-rate-limits

## Requirements
* Python 2.6 or 2.7
* Number of GCE instance running must be >= number of minimum zone spread count

## Third Party Libraries and Dependencies
The following libraries will be installed when you install the client library:
* [httplib2](https://github.com/jcgregorio/httplib2)
* [uri-templates](https://github.com/uri-templates/uritemplate-py)


## How Google Preemptible VM works (assumptions):
* Google needs to hold a certain amount of free compute resources as 'live stock' for growing customer needs or new demand. So Google sells unutilized compute resource at a lower price to reduce wastage
* If any interested party wants a non-preemptible instance (guaranteed uptime), Google stops preemptible instance when running out of free compute resources and sell those freed compute resources as non-preemptible instance for better profitability
* There are customers use-case who need massive non-preemptible instance for a few hours or a few days to perform processing. These customers then terminate the non-preemptible instance subsequently and their sudden request of massive non-preemptible instances sometimes cause preemptible instances to be terminated. Some examples include animation render farm, protein folding simulation, consumer analytics processing, and etc.
* Each zone is a datacenter, hence different zone will have different amount of 'live stock' compute resources and Google Preemptible VM instance(s) termination rate in different zones may vary


## Legend
* PE - Preemptible Instance
* NPE - Non-preemptible Instance
* MI-flag - Matured Instance
* NI-flag - New Instance
* RI-flag - Recycled Instance


## Algorithm concept
In order to keep preemptible instances running with very little interruption, GCE Manager needs to **"learn"** the termination rate of every zone and automatically move instances away from high termination rate zones to other zones evenly. The purpose of spreading out instances to preferred zones (i.e. zones with lower termination rate) evenly is to mitigate risk of drastic capacity drop in the event that massive termination activities occur in any zone. GCE Manager can be configured to restrict the minimum number of zones for instances to be spread evenly. To obtain termination rate metric, GCE Manager will keep track of both accumulated uptime for all instances running in selected zones and also termination event count for all instances that occurs in selected zones. Using a simple formula below, GCE Manager is able to assign a termination rate value for each zone to be used as deciding factor whether instances should be placed in any zone

Given that:
* U is accumulated uptime in hours (floating point value) of all instances in a zone
* T is accumulated termination event count of all instances in a zone
* To obtain termination rate value as R, take T divided by U so R = T/U

`Note: The lower value of R for a zone, the more preferred it is to be chosen`

Each newly created instance is marked with **NI-flag (New Instance)** and instance that has been running for more than 23 hours without downtime will be marked with **MI-flag (Matured Instance)**. If instances are terminated for the first time, it will be automatically restarted by GCE Manager instantly without re-evaluation of moving to other zone and **NI-flag** will be converted to **RI-flag (Recycled Instance)** or **MI-flag** will be converted to **NI-flag**. If instances with **RI-flag** is terminated, GCE Manager will re-evaluate termination rate in all zones and recreate those terminated instances in zones with lower termination rate. If no other zones having lower or same termination rate with affected zone, GCE Manager will use non-preemptible instance for 3 hours instead. Any recreated instances will be marked with **NI-flag**. When more than 50% of the zones having termination rate higher than a configured acceptable threshold, GCE Manager will start mixing usage of non-preemptible instance in those zones that exceed acceptable threshold for 3 hours until the total percentage of termination rate in all zone drops below 50%

As more uptime accumulated with lesser termination events among instances in all zones, the termination rate of zones that exceed acceptable threshold will drop eventually. Once the termination rate reaches an acceptable threshold in less than 50% of the zones, GCE Manager will continue using preemptible instances for all zones again.

`Note: Acceptable threshold is calculated based on the value set for GCE_NON_PREEMPTIBLE_INSTANCE_MIN_ALIVE_HOUR. For example, if 3 is the value set for it, then the termination rate threshold for a zone before using non-preemptible instance is (1/3) = 0.33333. 1 is a constant value for termination count, hence whenever termination happens more than once within 3 hours duration, then a zone is considered to have exceeded acceptable threshold`

## Future enhancements

Auto-scaling the number of running instances based on criteria specified in configuration

* Feedback or bugs report to: Teo Sze Siong [teo-at-binary-dot-com]
