"""ClawCode - Python AI Coding Assistant for Terminal

This is the main entry point for the ClawCode application.
"""

def main() -> None:
    # Import lazily so importing `clawcode` as a library does not require CLI deps.
    from clawcode.clawcode.cli.commands import cli

    cli()


if __name__ == "__main__":
    main()
