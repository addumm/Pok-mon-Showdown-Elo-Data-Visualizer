# for each distinct user in databse, check their rankings every X minutes (perhaps X = 3)?
# if rating stays the same in a format, don't add new row to database. if rating does change for specific format, add row
# also need to process new formats user might have started since adding their username to database

import schedule
import time
