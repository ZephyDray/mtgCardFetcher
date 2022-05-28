import yaml

from mtg_bot.bot import Bot

if __name__ == "__main__":
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    bot = Bot(config)
    bot.run()
