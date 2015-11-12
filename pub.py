from bs4 import BeautifulSoup
import os
import re
import urllib.request
import sqlite3
import operator
import datetime

HTMLFILE = "index.html"
VERBOSE = True            # yap about things as they're being worked through
RESET_DATABASE = False    # recreate database from scratch (instead of querying what we've got)
PURGE_LAST_SEASON = True  # no need to recreate the whole database from scratch.  just burn and re-parse the last season's page
LAST_SEASON = 39          # clunky, but easier than trying to load pages until I get a 404
DATABASE = "trivia.db"
SELECTED_TEAM = "xeditors"  # edit to highlight your own team, if you'd like!
DATA_SOURCE = "http://pubs.pubstumpers.com/index.cfm?DocID=Pub%20Profile&cn=68"   # edit to reflect your own location as needed
color_regex = re.compile("color:#(......)")

# cosmetic constants
TITLE_BGCOLOR = "333333"
TITLE_TEXTCOLOR = "ffffff"
CELL_TEXTCOLOR = "000000"

# map the color-coded placements on the website to their numerical ranks
RANKS = {
    'ff0000': 1,
    '273ed8': 2,
    '009933': 3,
    'ff9900': 4,
    '99009d': 5
}

TEAMS = {}

# push all the typo-strewn teams into the correctly unified bucket
# 'malformed name': "actual team name"
NORMALIZED = {
    't..a.t raffle': "there's always the raffle",
    'there always the raffle': "there's always the raffle",
    'there is always the raffl': "there's always the raffle",
    'theres always the raffle': "there's always the raffle",
    'schpadoinkle': "shapadoinkle",
    'o- thit': "oh thit",
    'o-thit': "oh thit",
    'o`thit': "oh thit",
    'oh thit !': "oh thit",
    'oh.thit': "oh thit",
    'wedunos': "wedunnos",
    'never qestion howard': "never question howard",
    'never question  howard': "never question howard",
    '10 min': "10 minute drum sole",
    '50 shades of gray': "50 shades of gary",
    '50 shads of gray': "50 shades of gary",
    '50shades of gary': "50 shades of gary",
    'beerswillers': "beer swillers",
    'audrey ciontreau': "audrey cointreau",
    'cheek-oh': "cheek oh",
    'game time folks': "gametime folks",
    'has any one seen my camel': "has anyone seen my camel",
    'choaos theory': "chaos theory",
    'photons': "the photons",
	'e=m c hammer': "e=mc hammer"
}

# god hates unicode
def removeNonAscii(s):
    return "".join(i for i in s if ord(i)<128)

# figure out what the "real" team is for random possibly-fat-fingered website names
def normalize_team_name(name):
    if (name in NORMALIZED):
        return NORMALIZED[name]
    else:
        return name
    
# takes an HTML color hex code, returns the rank it equates to (0 if we don't know) 
def get_rank(html):
    color_match = color_regex.search(html)
    if (color_match):
        color_hex = color_match.group(1)
        return RANKS[color_hex]
    else:
        return 0

# get the HTML page for Season #<season> of PubStumpers trivia
# if we already have a local file, don't attempt to redownload things.
# otherwise: nab the missing file via HTTP
def get_season(season, overwrite=False):
    season = str(season)
    output = "season" + season + ".html"
    url = DATA_SOURCE + "&season=" + season
    
    if (os.path.exists(output)):
        if (overwrite):
            print(("removing {:s} as requested").format(output))
            os.remove(output)
        elif (VERBOSE):
            print("already have " + output +", ignoring request.")
            return
    
    if (VERBOSE): print("getting season " + season + "... ")
    urllib.request.urlretrieve(url, output)
    if (VERBOSE): print("done.")
 
# for a given season, look through its page of HTML and store the bits we care about in a database
def parse_season(season):
    # read the whole file into a single variable
    season = str(season)
    f = open("season" + season + ".html")
    text = f.read()
    text = text.replace("&copy;", "")	# the copyright symbol breaks some things.  let's not even deal.
    f.close()

    # let BeautifulSoup deal with parsing the train wreck of the trivia HTML
    soup = BeautifulSoup(text)
    
    c = conn.cursor()
    all_results = soup.find_all("td", align="left", colspan=None)   # get all the TD containing team names
    for team_data in all_results:
        team_name = str(team_data.get_text(strip=True))
        if (VERBOSE): print("team: " + team_name)
        team_name = normalize_team_name(team_name.lower())
        TEAMS[team_name] = 1
        
        score_data = team_data.next_sibling.next_sibling            # advance to first weekly score
        week = 0
        rank = -1                                                   # weekly placement? (0 = showed up) (-1 = didn't show up) (else = rank)
        while (score_data is not None):
            if (score_data.has_attr('align')):                      # final tally score - no color, presented as decimalized number
                for total_score in score_data.stripped_strings:
                    total_score = float(total_score)
                    if (VERBOSE): print("TOTAL: " + str(total_score))
                    c.execute("INSERT INTO season_results VALUES (?,?,?)", (season, team_name, total_score))
                    conn.commit()
                    
            else:                                                   # weekly score: integer, possibly colored
                week = week + 1
                style = score_data.get('style')
                if (style is not None):
                    rank = get_rank(style)                          # see what rank this result maps to, if any
                else:
                    rank = 0
                 
                for score in score_data.stripped_strings:
                    score = int(score)
                    if (score == 0):                                # zero scores map to non-attendance (rank -1, to differentiate)
                        rank = -1
                    if (VERBOSE): print("WEEK: " + str(week) + "  SCORE: " + str(score) + "  RANK: " + str(rank))
                    c.execute("INSERT INTO weekly_results VALUES (?,?,?,?,?)", (season, team_name, week, rank, score))
                    conn.commit()

            score_data = score_data.next_sibling.next_sibling       # advance to next weekly score, if it exists
        
        if (VERBOSE): print("~~~")

# return a connection to the database
# (deleting the database and recreating its core tables, if so desired)
def connect_database():
    if (RESET_DATABASE):
        if (os.path.exists(DATABASE)):
            os.remove(DATABASE)

    conn = sqlite3.connect(DATABASE)
    
    if (RESET_DATABASE):        # burn the world, recreate empty tables to be re-filled
        c = conn.cursor()
        c.execute("CREATE TABLE weekly_results (season INTEGER, team TEXT, week INTEGER, rank INTEGER, score REAL)")
        c.execute("CREATE TABLE season_results (season INTEGER, team TEXT, score REAL)")
        conn.commit()
    elif (PURGE_LAST_SEASON):
        c = conn.cursor()
        c.execute("DELETE FROM weekly_results WHERE season=?", [LAST_SEASON])
        c.execute("DELETE FROM season_results WHERE season=?", [LAST_SEASON])
    
    return(conn)
 
# takes a title for the table, an array of column headers, and an array of tuples with table data
# the number of column headers and the number of non-bool elements per tuple should match
# prints to the writefile that data in pretty HTML form
def print_table(title, header_arr, data):
    global writefile

    # top of the table and table title row
    writefile.write('<TABLE BORDER=1 CELLPADDING=3 CELLSPACING=4 BGCOLOR="eeeeee">\n')
    writefile.write('<TR>\n<TH BGCOLOR="{:s}" ALIGN="CENTER" COLSPAN={:d}><FONT COLOR="{:s}">{:s}</FONT></TH>\n</TR>\n'.format(TITLE_BGCOLOR, len(header_arr), TITLE_TEXTCOLOR, title))
    
    # print out all the column headers
    writefile.write('<TR>\n')
    for header in header_arr:
        writefile.write('<TH>{:s}</TH>\n'.format(header))
    writefile.write('</TR>\n')
    
    for row in data:
        writefile.write('<TR>\n')
        btag = ""
        otag = ""
        ctag = ""
        if ((SELECTED_TEAM in row) or (SELECTED_TEAM in str(row[1])) or ((len(row)>2) and (SELECTED_TEAM in str(row[2])) and (header_arr[2]=='Winner'))):    # our team is special! highlight those rows.
            btag = ' BGCOLOR="ffff00"'
            otag = '<FONT COLOR=0000ff><b>'
            ctag = '</b></FONT>'
        if (type(row[-1]) is bool and row[-1]):                     # streak data contains an "is current?" bool as its last item.  format special if true
            otag = '<FONT COLOR=ff0000><b>'
            ctag = '</b></FONT>'
        for element in row:
            if type(element) is not bool:                           # don't print out ugly "is current?" in text form
                writefile.write('<TD ALIGN="CENTER"{:s}>{:s}{:s}{:s}</FONT></TD>\n'.format(btag, otag, str(element).title().replace("'S", "'s"), ctag))
        writefile.write('</TR>\n')
    writefile.write('</TABLE>\n')

# return a list of all the seasons where we have honest-to-gosh results
def get_seasons():
    c = conn.cursor()
    
    seasons = []
    season_rows = c.execute("SELECT DISTINCT season FROM season_results")
    for row in season_rows:
        seasons.append(row[0])
    return(seasons)

# get all the seasons and weeks that actually existed with scores, ordered from first to last
# return that data as a list of (season, week) tuples
def get_season_weeks():
    c = conn.cursor()
    
    season_weeks = []
    season_weeks_rows = c.execute("SELECT DISTINCT season, week FROM weekly_results ORDER BY season ASC, week ASC")
    for row in season_weeks_rows:
        season_weeks.append(row)

    return(season_weeks)

# sometimes, we'll have data from weeks that never "really" existed.
# or "weeks" that are from the current ongoing season that are still in the future, so they haven't happened yet.
# we should get rid of those.
def clean_database():
    season_weeks = get_season_weeks()
    c = conn.cursor()
    
    weeks_to_unexist = []
    seasons_to_unexist = {}
    for season_week in season_weeks:
        (season, week) = season_week
        max_score_rows = c.execute("SELECT MAX(score) FROM weekly_results WHERE season={:d} AND week={:d}".format(season, week))
        max_score_tuple = max_score_rows.fetchone()
        max_score = max_score_tuple[0]
        if (VERBOSE): print(season, week, max_score)
        if (not max_score):         # top score for the week was 0?  yeah, that week wasn't real.
            if (VERBOSE): print("S{:d} W{:d} was not 'real' - tagging for deletion.".format(season, week))
            weeks_to_unexist.append(season_week)
            seasons_to_unexist[season] = True   # any season with an "unreal" week probably isn't legit in its own right.  purge it.
    
    # delete every week where the week's data was garbage
    for non_week in weeks_to_unexist:
        c.execute("DELETE FROM weekly_results WHERE season=? AND week=?", non_week)
        conn.commit()
    
    # delete every season that had a garbage week going on at some point
    for non_season in seasons_to_unexist:
        c.execute("DELETE FROM season_results WHERE season=?", [non_season])
        conn.commit()
    
# getting streak information out of the database is not a simple, straightforward query
# break that ordeal into this function here
def get_streaks():
    streaks = []
    current_streaks = {}
    season_weeks = get_season_weeks()
    c = conn.cursor()
    
    # for each real week, get the teams that had a score that counted
    for season_week in season_weeks:
        team_tuples = c.execute("SELECT team FROM weekly_results WHERE rank!=-1 AND season=? AND week=?", season_week)
        teams = []
        for element in team_tuples:
            teams.append(element[0])
        
        for team in teams:
            if (VERBOSE): print("++++" , team, "++++")
            # if you were present: increment (or start) your streak in the current_streak dict
            if (team in current_streaks):
                if (VERBOSE): print("UP IT")
                current_streaks[team] = current_streaks[team] + 1
            else:
                if (VERBOSE): print("NOOB")
                current_streaks[team] = 1
                
        # for all teams with current streaks: if the streak was broken, move that to "streaks" and end current streak
        ended_streaks = []
        for streak in current_streaks:
            if (not streak in teams):
                if (VERBOSE): print("*** {:s} ***".format(streak))
                if (VERBOSE): print("NOT HERE")
                streaks.append((streak, current_streaks[streak], season_week[0], season_week[1], False))
                ended_streaks.append(streak)
                
        for streak in ended_streaks:
            del current_streaks[streak]
        
    # make sure current streaks appear in the list of all-time streaks, too
    for streak in current_streaks:
        streaks.append((streak, current_streaks[streak], season_week[0], season_week[1], True))

    # sort current streaks by length
    current_streaks = sorted(current_streaks.items(), key=lambda x: x[1])
    current_streaks.reverse()
    
    # sort historical streaks by length, only take top 20
    streaks.sort(key=operator.itemgetter(1))
    streaks.reverse()
    streaks = streaks[:20]
    return(streaks, current_streaks)
    
# break all the seasonal margin-of-victory stuff down into one simple function call here
def get_season_margins_of_victory():
    c = conn.cursor()
    
    # get a list of all the seasons that actually existed
    seasons = get_seasons()
    results = []
    
    # for every season: get the two top scores, calculate the difference, jam the (season, winner, loser, delta) tuple into the return array
    for season in seasons:
        top_two = c.execute("SELECT team, score FROM season_results WHERE season={:d} ORDER BY score DESC LIMIT 2".format(season))
        top_two_tuples = top_two.fetchall()
        if (len(top_two_tuples)==2):
            (win_team, win_score) = top_two_tuples[0]
            (lose_team, lose_score) = top_two_tuples[1]
            margin = win_score - lose_score
            results.append((season, "{:s} ({:.0f})".format(win_team, win_score), "{:s} ({:.0f})".format(lose_team, lose_score), margin))
    results.sort(key=operator.itemgetter(3))    # sort on the margin of victory
    results.reverse()
    return(results)

# break all the weekly margin-of-victory stuff down into one simple function call here
def get_week_margins_of_victory():
    season_weeks = get_season_weeks()
    results = []
    c = conn.cursor()
          
    # for every season and week: get the two top scores, calculate the difference, jam the (season, week, winner, loser, delta) tuple into the return array
    for (season, week) in season_weeks:
        top_two = c.execute("SELECT team, score FROM weekly_results WHERE season={:d} AND week={:d} ORDER BY score DESC LIMIT 2".format(season, week))
        (win_team, win_score) = top_two.fetchone()
        (lose_team, lose_score) = top_two.fetchone()
        margin = win_score - lose_score
        results.append((season, week, "{:s} ({:.0f})".format(win_team, win_score), "{:s} ({:.0f})".format(lose_team, lose_score), margin))
    results.sort(key=operator.itemgetter(4))    # sort on the margin of victory
    results.reverse()
    results = results[:20]                      # only take the top 20 results
    return(results)

# return a list of (team -> number of season wins) pairs for the history of trivia
def get_seasons_won_by_team():
    c = conn.cursor()

    # step one: get a list of seasons
    seasons = get_seasons()
    team_wins = {}
    
    # for every season: get the top score for that season
    for season in seasons:
        top_score_rows = c.execute("SELECT MAX(score) FROM season_results WHERE season={:d}".format(season))
        top_score = top_score_rows.fetchone()
        top_score = top_score[0]
        
        # get the list of teams that had the top score for a given season (could be more than one!)
        winning_teams = c.execute("SELECT team FROM season_results WHERE season={:d} AND score={:f}".format(season, top_score))
        winning_team_tuples = winning_teams.fetchall()
        if (VERBOSE): print(winning_team_tuples)
        
        # for every team with the top score: give a fractional victory depending on how many teams won out
        for team_tuple in winning_team_tuples:
            team = team_tuple[0]
            num_wins = 0.0
            if (team in team_wins):
                num_wins = team_wins[team]
            num_wins = num_wins + (1/len(winning_team_tuples))  # "enjoy your third of a win or whatevs."
            team_wins[team] = num_wins
    
    # sort by the number of wins, then return
    team_wins = sorted(team_wins.items(), key=lambda x: x[1])
    team_wins.reverse()
    return(team_wins)
 
 #def get_highest_average_scores():
 #   c.execute("SELECT UNIQUE team, AVG(score) as avrij FROM weekly_results ORDER BY avrij DESC")
 
# assuming there's a database full of interesting information: look at it.
# do some clever queries and print a mess of tables based on what all we can find
def analyze_database():
    global writefile
    c = conn.cursor()
    
    # write out HTML header
    writefile.write('<HTML>\n<HEAD>\n<TITLE>PubStumpers Trivia Info Dump</TITLE>\n</HEAD>\n<BODY BGCOLOR="999999" TEXT="000000" LINK="CCCCCC" VLINK="CCCCCC" ALINK="FFFFFF">\n')
    now = datetime.datetime.now()
    now_string = datetime.date.strftime(now, "%a %Y-%b-%d %H:%M")
    writefile.write('<FONT COLOR="ffffff">')
    writefile.write('<i>Page created at {:s}.</i> '.format(now_string))
    writefile.write('<i>Data analyzed procured from <a href="{:s}">this source</a>.</i><p />'.format(DATA_SOURCE))
    writefile.write('</FONT>')
    
    # query for data and use it to print out every remotely interesting table
    #highest_average_scores = c.execute("SELECT team, AVG(score) as avrij FROM weekly_results WHERE score!=0 GROUP BY team ORDER BY avrij DESC")
    #print_table("Highest Average Scores", ["Team", "Average"], highest_average_scores)

    highest_scores_ever = c.execute("SELECT team, season, week, score, rank FROM weekly_results WHERE team='{:s}' ORDER BY score DESC, season DESC, week DESC LIMIT 20".format(SELECTED_TEAM))
    print_table("Highest {:s} Weeks Ever".format(SELECTED_TEAM), ["Team", "Season", "Week", "Score", "Rank"], highest_scores_ever)
	
    best_seasons_ever = c.execute("SELECT team, season, score FROM season_results ORDER BY score DESC, season DESC LIMIT 20")
    print_table("Best Seasons Ever", ["Team", "Season", "Score"], best_seasons_ever)
    
    season_wins_by_team = get_seasons_won_by_team()
    print_table("Seasons Won By Each Team", ["Team", "Seasons Won"], season_wins_by_team)

    margins_data = get_season_margins_of_victory()
    print_table("Season Margins of Victory", ["Season", "Winner", "Runner Up", "Margin"], margins_data)

    week_margins_data = get_week_margins_of_victory()
    print_table("Biggest Weekly Margins of Victory", ["Season", "Week", "Winner", "Runner Up", "Margin"], week_margins_data)
    
    raw_first_place_showings = c.execute("SELECT team, COUNT(rank) FROM weekly_results WHERE rank='1' GROUP BY team ORDER BY COUNT(rank) DESC")
    first_place_showings = []
    for tuple in raw_first_place_showings:
        if (tuple[1]>2):        # limit ourselves to teams that took first place at least twice
            first_place_showings.append(tuple)
    print_table("First Place Finishes Ever", ["Team", "1st Place Finishes"], first_place_showings)

    lowest_firsts = c.execute("SELECT team, season, week, score FROM weekly_results WHERE rank='1' ORDER BY score ASC, season DESC LIMIT 20")
    print_table("Lowest First Place Scores", ["Team", "Season", "Week", "Score"], lowest_firsts)
    
    best_weeks_ever = c.execute("SELECT team, season, week, score FROM weekly_results WHERE season>5 ORDER BY score DESC, season DESC LIMIT 20")
    print_table("Highest Scoring Weeks Ever (After Season 5)", ["Team", "Season", "Week", "Score"], best_weeks_ever)
    
    (streaks, current_streaks) = get_streaks()
    print_table("Longest Consecutive Weeks Streaks", ["Team", "Weeks", "Season #", "Week #"], streaks)
    print_table("Active Consecutive Weeks Streaks", ["Team", "Weeks"], current_streaks)
 
    total_points_ever = c.execute("SELECT team, SUM(score) AS total FROM weekly_results GROUP BY team ORDER BY total DESC LIMIT 20")
    print_table("Total Points Ever", ["Team", "Cumulative Score"], total_points_ever)

    total_showings_ever = c.execute("SELECT team, COUNT(*) AS shows FROM weekly_results WHERE rank!='-1' GROUP BY team ORDER BY shows DESC LIMIT 20")
    print_table("Total Showings Ever", ["Team", "Times Present"], total_showings_ever)

    # write out HTML footer
    writefile.write('</BODY>\n</HTML>\n')

# MAIN PROGRAM STARTS HERE
#
start_time = datetime.datetime.now()

# connect to (or create) the database   
conn = connect_database()

# download and read in files, if necessary
seasons = []
if (PURGE_LAST_SEASON):
	seasons.append(LAST_SEASON)
if (RESET_DATABASE):
    seasons = list(range(1, LAST_SEASON+1))

for season in seasons:
	get_season(season, PURGE_LAST_SEASON)
for season in seasons:
	parse_season(season)
clean_database()

# print neat things about all that data
writefile = open(HTMLFILE, "w")
analyze_database()
writefile.close()

# clean up shop
conn.close()

end_time = datetime.datetime.now()
duration = end_time - start_time
print("PROGRAM RAN FOR: " + str(duration))

exit(0)
