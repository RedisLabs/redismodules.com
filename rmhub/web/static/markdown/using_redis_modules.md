Generally, modules have their own documentation that explains how to use them.
To start using most open source modules with open source Redis, follow these steps:

- Clone or download the source code from the module's repository
- Follow the instructions in the repository for building the module (usually just running the `make` in a terminal)
- Load the module to the Redis server with the `loadmodule` configuration directive or the [`MODULE LOAD` command](https://redis.io/commands/module-load)
- Use any Redis client to connect to the server and call the module's commands

Certified modules that are included with [<span class="redisefont">redis<sup>e</sup></span>](https://redislabs.com/why-redis/redis-enterprise/) only need to be activated for a database to be used.

Refer to the [<span class="redisefont">redis<sup>e</sup></span> documentation](https://redislabs.com/resources/documentation/) for more details. 