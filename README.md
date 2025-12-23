## Motivation
Seeing that there are not many progress tracking data visualization tools for pokemon (specifically pokemon showdown) compared to many other online games, I decided to build one myself. 
Displaying elo time series data was the main goal, which had been done previously, thus much inspiration is drawn from https://pokemonshowdownuserstats.com/ ([git](https://github.com/pnbruce/pokemon-showdown-user-stats)). 
Other inspiration is indirectly drawn from [op.gg](op.gg) as my little brother plays Leage of Legends.  


## App Functionality Overview
My idea was to use the flask framework in python to develop a web app that produces interactive visualizations. 
This soon turned into a hybrid flask-dash web app to ensure plotly (the data visualization library used) runs smoothly.
The core functionality of the app is intaking pokemon showdown account usernames, calling the pokemonshowdown API for the account ratings, and storing the user and ratings for each ladder format in a postgres database. 
To track the accounts, there is a rate scheduled task to call the pokemonshowdown API and fetch the ratings/elo/gxe/etc. of each distinct user in the database, then add new ratings to the database. 
New formats played are automatically handled thanks to this. 
I should also note that I used this project as an opportunity to learn more about docker and AWS, thus the app is containerized via docker and deployed through AWS.


## How to use
Input a valid Pokemon Showdown account username. The first time a particular username is inputted, the rating tracking begins for that user and data points for formats start to be gathered. 
After playing some games, you can come back and view your progress by inputting your name again (or refreshing the page), choosing a format, and clicking submit. 
Each time you want to select a new format to view, you select the desired format in the format drop down and click submit. 
If you input an account with no games played, you may notice that the 'None' format is the only format. This is a filler format for elo tracking to handle these fresh accounts.


## Future work
In the future, I hope to add a "recent teams used" section that is effectively a mini replay scouter. 
I think with that, the app will be an even more helpful tool especially in the context of ladder tournaments (as being able to see an opponents elo trajectory, gxe, and recent games played/teams used can be a major leg up). 



If you have [ideas for features or want to report a bug](https://forms.gle/aoUWYswA7bMMN4w8A), please fill out the form! 
If you would like to help contribute to the project, you can add me on discord @oklol8061.

