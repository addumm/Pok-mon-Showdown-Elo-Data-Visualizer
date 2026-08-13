# [showdownstats.com](https://showdownstats.com/)
![showdownstats](https://github.com/addumm/Pok-mon-Showdown-Elo-Data-Visualizer/blob/main/Screenshot%202026-08-12%20at%205.07.48%E2%80%AFPM.png)


## Motivation
Seeing that there are not many progress progress tracking tools for pokemon (specifically pokemon showdown) compared to many other online games, I decided to build one myself. 
Displaying elo time series data was the main goal, which had been done previously, thus much inspiration is drawn from https://pokemonshowdownuserstats.com/ ([git](https://github.com/pnbruce/pokemon-showdown-user-stats)). I've added a few more features I thought were cool, such as win/loss visualization, peak rating/GXE data, and recent replays and teams used. Other inspiration is indirectly drawn from [op.gg](op.gg) as my little brother plays Leage of Legends. 


## App Functionality Overview
My idea was to use the flask framework in python to develop a web app that produces interactive visualizations. 
This soon turned into a hybrid flask-dash web app to ensure plotly runs smoothly.
The core functionality of the app is intaking pokemon showdown account usernames, hitting the pokemonshowdown API for the account ratings and replay data, then storing the user and ratings for each ladder format in a postgres database.
To track the accounts, I've made cron job to hit the pokemonshowdown API and fetch the ratings/elo/gxe/replays/teams etc. of each distinct user in the database, then add new ratings to the database.
New formats played are automatically handled thanks to this. 
I used this project as an opportunity to learn how to use docker and AWS, thus the app is containerized via docker and (was) deployed through AWS. I have since switched to Render.
I learned much about the concurrency and optimization methods that are frequently used in data-intensive apps. Seeing the difference in time that multithreading and caching made on my own project was quite eye-opening.


## How to use
Input a registered Pokemon Showdown account username. The first time a particular username is inputted, the tracking begins for that user and data points for formats will then be gathered from that point on. 
After playing some games, you can come back and view your progress by inputting your name again (or refreshing the page), choosing a format, and clicking submit. 
Each time you want to select a new format to view, you select the desired format in the format drop down and click submit. 
If you input an account with no games played, you may notice that the 'None' format is the only format. This is a filler format for elo tracking to handle these fresh accounts.


If you have [ideas for features or want to report a bug](https://forms.gle/aoUWYswA7bMMN4w8A), please fill out the form! 
If you would like to help contribute to the project, you can add me on discord @oklol8061.

