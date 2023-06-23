
import logging
import utils
import app

logging.basicConfig(
    format='[%(asctime)s] - <%(name)s> %(levelname)s: %(message)s',
    level=logging.INFO,
    handlers=[
        app.logging.Console,
        app.logging.File
    ]
)

def main():
    utils.setup()
    app.run()

if __name__ == "__main__":
    main()
