# Deck

Deck is a work in progress api/score server, designed for older osu! clients.

Please view [this repository](https://github.com/Lekuruu/titanic) for setup instructions!

## What works?

A lot of the features are pretty much done for the most part:

- [x] Avatars
- [x] Error Handling
- [x] Menu Icon
- [x] Screenshots
- [x] Ratings
- [x] Comments
- [x] Favourites
- [x] Leaderboards
- [x] Replays
- [x] Score Submission
- [x] [Circleguard](https://github.com/circleguard) anticheat reports
- [x] Bot messages on #highlight

## What is left to do?

- [ ] Direct
- [ ] Achievements
- [ ] Client Updates
- [ ] Improved logging
- [ ] Beatmap imports
- [ ] Customized .osu files
- [ ] API for frontend use
- [ ] (Monthly Charts)
- [ ] (Beatmap Submission)

and probably a lot more stuff.

#### About osu!direct

For osu!direct to work properly, I need to make some changes to the database
so that beatmaps include attributes like:
- osz_filesize
- has_storyboard
- query_string

The query string will be important for searching.
I also want to create a beatmap scraper that can automatically add beatmaps to a database.
