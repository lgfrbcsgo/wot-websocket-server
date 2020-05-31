#!/usr/bin/python

import sys

content = """
<root>
    <id>lgfrbcsgo.websocket-server</id>
    <version>{version}</version>
    <name>Websocket Server</name>
    <description>A single threaded, non blocking Websocket server for WoT mods which makes use of the `async` / `await`.</description>
</root>
"""

print(content.format(version=sys.argv[1]))
