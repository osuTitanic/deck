
import logging
import app

logging.basicConfig(
    format='[%(asctime)s] - <%(name)s> %(levelname)s: %(message)s',
    level=logging.INFO
)

def main():
    app.run()

if __name__ == "__main__":
    main()
