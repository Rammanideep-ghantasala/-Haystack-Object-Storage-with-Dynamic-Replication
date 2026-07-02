#!/bin/bash

# echo "WARNING: This will delete ALL Docker containers, images, volumes, networks and data."
# read -p "Are you sure? (yes/no): " confirm

# if [[ "$confirm" != "yes" ]]; then
#     echo "Aborted."
#     exit 0
# fi

echo "Stopping all containers..."
docker stop $(docker ps -aq) 2>/dev/null

echo "Removing all containers..."
docker rm -f $(docker ps -aq) 2>/dev/null

echo "Removing all images..."
docker rmi -f $(docker images -aq) 2>/dev/null

echo "Removing all volumes..."
docker volume rm -f $(docker volume ls -q) 2>/dev/null

echo "Removing all custom networks..."
docker network rm $(docker network ls --filter "type=custom" -q) 2>/dev/null

echo "Pruning system (cache, build cache)..."
docker system prune -a --volumes -f

# echo "OPTIONAL: Removing /var/lib/docker (entire docker storage)"
# read -p "Delete /var/lib/docker too? This resets Docker completely. (yes/no): " confirm2

# if [[ "$confirm2" == "yes" ]]; then
#     echo "Stopping Docker service..."
#     sudo systemctl stop docker

#     echo "Deleting /var/lib/docker..."
#     sudo rm -rf /var/lib/docker

#     echo "Starting Docker service..."
#     sudo systemctl start docker

#     echo "Docker storage reset complete."
# fi

echo "All Docker data cleaned successfully!"
