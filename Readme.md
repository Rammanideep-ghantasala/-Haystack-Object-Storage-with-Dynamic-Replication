# **Haystack Object Store**

Haystack Object Store is a distributed object storage system designed for scalability, fault tolerance, and high availability. It uses a combination of consistent hashing, replication, and caching to efficiently store and retrieve objects. The system is implemented using Python and FastAPI, with Redis as the metadata store and NGINX as the load balancer.

---

## **Table of Contents**

* [Architecture](#architecture)
* [Components](#components)
* [Features](#features)
* [Setup and Deployment](#setup-and-deployment)
* [API Endpoints](#api-endpoints)
* [Directory Structure](#directory-structure)

---

## **Architecture**

The Haystack Object Store consists of the following key components:

1. **Directory Service**: Manages metadata for object placements and active nodes.
2. **Store Service**: Stores objects persistently on disk with support for compaction and caching.
3. **Cache Service**: Provides an in-memory cache for frequently accessed objects.
4. **Replication Manager**: Dynamically adjusts the replication factor of objects based on access patterns.
5. **Webserver**: Acts as the API gateway for clients, handling object uploads, retrievals, and deletions.
6. **NGINX**: Load balances requests across multiple webserver instances.
7. **Redis Cluster**: Stores metadata for membership and object placements.

---

## **Components**

### **1. Directory Service**

* **Purpose**: Tracks active nodes and object placements.
* **Code**: Located in `directory-service/app/`.
* **Key Files**:

  * `state.py`: Manages Redis-backed metadata for nodes and placements.
  * `router.py`: Provides APIs for node registration, heartbeats, and placement management.

### **2. Store Service**

* **Purpose**: Stores objects persistently on disk.
* **Code**: Located in `store-service/app/`.
* **Key Files**:

  * `engine.py`: Implements the storage engine with support for compaction and in-memory caching.
  * `router.py`: Provides APIs for object storage, retrieval, and deletion.

### **3. Cache Service**

* **Purpose**: Provides an in-memory cache for objects.
* **Code**: Located in `cache-service/app/`.
* **Key Files**:

  * `cluster.py`: Manages membership and heartbeats with the directory service.
  * `router.py`: Provides APIs for caching objects.

### **4. Replication Manager**

* **Purpose**: Dynamically adjusts the replication factor of objects based on access patterns.
* **Code**: Located in `replication-manager/app/`.
* **Key Files**:

  * `replicator.py`: Implements the logic for scaling replicas up or down.
  * `router.py`: Provides APIs for recording access patterns.

### **5. Webserver**

* **Purpose**: Acts as the API gateway for clients.
* **Code**: Located in `webserver/app/`.
* **Key Files**:

  * `router.py`: Provides APIs for object uploads, retrievals, and deletions.
  * `hash_ring.py`: Implements consistent hashing for cache node selection.

### **6. NGINX**

* **Purpose**: Load balances requests across multiple webserver instances.
* **Configuration**: Defined in `nginx.conf`.

---

## **Features**

* **Distributed Storage**: Objects are distributed across multiple store nodes.
* **Replication**: Objects are replicated across multiple nodes for fault tolerance.
* **Consistent Hashing**: Ensures efficient distribution of objects across cache nodes.
* **Dynamic Scaling**: Replication factor is adjusted dynamically based on access patterns.
* **Caching**: Frequently accessed objects are cached in memory for faster retrieval.
* **Compaction**: Store nodes periodically compact data to reclaim space.

---

## **Setup and Deployment**

### **Prerequisites**

* Docker and Docker Compose installed on your system.

### **Steps**

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd Haystack-Object-Store
   ```

2. Build and start the services:

   ```bash
   docker-compose up --build
   ```

3. Access the web interface:
   Open your browser and navigate to:
   **[http://localhost](http://localhost)**

4. Interact with the API:
   Use tools like **curl**, **Postman**, or your browser.

5. Stop and clean up:

   ```bash
   docker-compose down
   ```

---

## **API Endpoints**

### **Directory Service**

* `POST /join`: Register a node.
* `POST /heartbeat`: Send a heartbeat.
* `GET /nodes`: List active nodes.
* `GET /placements/{key}`: Get object placement.
* `POST /placements/{key}`: Set object placement.
* `DELETE /placements/{key}`: Delete object placement.

### **Store Service**

* `GET /object/{key}`: Retrieve an object.
* `POST /object/{key}`: Store an object.
* `DELETE /object/{key}`: Delete an object.

### **Cache Service**

* `GET /get/{key}`: Retrieve a cached object.
* `POST /set/{key}`: Cache an object.
* `POST /invalidate/{key}`: Invalidate a cached object.

### **Webserver**

* `GET /object/{key}`: Retrieve an object (with caching).
* `POST /object`: Upload an object.
* `DELETE /object/{key}`: Delete an object.

---

## **Directory Structure**

```
Haystack-Object-Store/
├── cache-service/
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
├── directory-service/
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
├── replication-manager/
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
├── store-service/
│   ├── app/
│   ├── data/
│   ├── Dockerfile
│   └── requirements.txt
├── webserver/
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
├── nginx.conf
└── docker_nuke.sh
```

---