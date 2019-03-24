import re


def ping(command, label, config):
    print(command.get("msg", "ping"), "pong!")


def versionbump(command, label, config):
    level = (
        "major"
        if command.get("major")
        else "minor"
        if command.get("minor")
        else "bugfix"
    )

    def bump(match):
        major, minor, bugfix = map(int, match.group(1).split("."))
        if level == "major":
            major += 1
            minor = bugfix = 0
        elif level == "minor":
            minor += 1
            bugfix = 0
        else:
            bugfix += 1
        return f'version="{major}.{minor}.{bugfix}"'

    with open("setup.py") as f:
        old = f.read()
    with open("setup.py", "w") as f:
        for line in old.split("\n"):
            if "version" not in line:
                f.write(line)
            else:
                f.write(re.sub(r'version="([^"]+)"', bump, line))
            f.write("\n")
