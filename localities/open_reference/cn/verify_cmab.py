"""Re-download the two directories and the map layer to check their pinned bytes."""

from urllib.request import urlopen

from . import _check_bytes, _source


def main():
    source = _source()
    files = {**source["files"], "map": source["map_source"]}
    for language, descriptor in files.items():
        with urlopen(descriptor["url"], timeout=25) as response:
            data = response.read(descriptor["bytes"] + 1)
        _check_bytes(data, descriptor)
        print(f"{language} {descriptor['sha256']}")


if __name__ == "__main__":
    main()
