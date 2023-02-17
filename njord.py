import argparse
import os, signal
import re
import requests
import subprocess
import sys
import time
import traceback
import urllib.request
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions

# Measure runtime of the script
startTime = time.time()

# Set exit code var
exitCode = 0 

# Initialize the first error
firstError = True

# Set up named arguments
parser=argparse.ArgumentParser()
parser.add_argument('-d', '--domain', help='Base URL of your portal, including the protocol; e.g. https://docs.kontent.ai', required=True)
parser.add_argument('-f', '--folder', help='Folder (subportal) on your website, e.g. tutorials', required=False, default="")
parser.add_argument('-x', '--no-external', help="Do not check external pages (ie. pages outside the domain)", required=False, action='store_true')
parser.add_argument('-s', '--sitemap', help='Specify full sitemap URL manually', required=False, default="")
parser.add_argument('-q', '--quiet', help='Do not print warnings, only info and errors.', required=False, action='store_true')
parser.add_argument('-v', '--verbose', help='Be very verbose and print time spent on each (larger) operation', required=False, action='store_true')
args=parser.parse_args()
domain = args.domain
folder = args.folder
manualSitemapLoc = args.sitemap
noExternal = args.no_external
beQuiet = args.quiet
beVerbose = args.verbose

# If 'folder' doesn't begin with slash, add it. If 'folder' is empty, initialize it with an empty string.
if not re.match('/', folder):
	folder = "/" + folder
if folder is None:
	folder = ""

# It's easier to work with the whole path.
URLPath = domain + folder

# Initialize headless Firefox browser we'll need to get cumbersome JS-generated pages like KL reference (this can be pretty slow BTW)
opts = FirefoxOptions()
opts.add_argument("--headless")

# The executable_path isn't mandatory if geckodriver is in PATH
# browser = webdriver.Firefox(options=opts, executable_path='/usr/bin/geckodriver')
browser = webdriver.Firefox(options=opts)

# Define colors (if the OS we're on is Windows, drop that and just fill them with empty strings because colors in command prompt on Windows are too much pain)
if sys.platform != 'win32':
	class color:
		PURPLE = '\033[95m'
		CYAN = '\033[96m'
		DARKCYAN = '\033[36m'
		BLUE = '\033[94m'
		GREEN = '\033[92m'
		YELLOW = '\033[93m'
		RED = '\033[91m'
		BOLD = '\033[1m'
		UNDERLINE = '\033[4m'
		END = '\033[0m'
else:
	class color:
		PURPLE = ''
		CYAN = ''
		DARKCYAN = ''
		BLUE = ''
		GREEN = ''
		YELLOW = ''
		RED = ''
		BOLD = ''
		UNDERLINE = ''
		END = ''

def printNOK(pg="", ln="", first=False, type=None, redir="", errorCode=""):
	# exitCode is global variable so we must declare here that we want to work with the global var, not its local instance inside this function
	global exitCode
	internalExitCode = exitCode

	# Decide whether to print the headline (which page has issues). The logic behind this is:
	# We print the headline only if it's the 1st error for the page. But if the --quiet switch is on and the issue is only warning (3 types - absorel, unreachable, and cantGoOutside), then we mustn't print the headline because it'd be only headline and no issue beneath it (we don't print warnings when we're told to be quiet).
	# BTW - removed exitCode = 1 from the warnings so they don't cause the script to end with failure (because they're not essentially a failure).
	if first == True  \
		and not (beQuiet == True  \
 				  and (   type == 'absorel'  \
 				       or type == 'unreachable'  \
 				       or type == 'cantGoOutside'  \
 				       or type == 'GHLineHilight'  \
 				       or type == 'externalNOK')  \
 				  or type == 'sitemapNotFound' \
 				):
		print("Issues in " + color.BOLD + pagesLinksAndAnchors[page]['title'] + color.END + " (" + pg + ")")

	# outside page thru 404
	if type == '404':
		print(color.RED + color.BOLD + "##vso[task.logissue type=error] Outsite link unreachable: " + color.END + ln)
		internalExitCode = 1
		first = False

	# Remote sitemap not found
	elif type == 'sitemapNotFound':
		print(color.RED + color.BOLD + "##vso[task.logissue type=error] Remote sitemap not found under this URL: " + color.END + ln)
		internalExitCode = 1
		first = False

	# internal page thru 404
	elif type == 'internalSitemap404':
		print(color.RED + color.BOLD + "##vso[task.logissue type=error] URL in the sitemap unreachable: " + color.END + ln)
		internalExitCode = 1
		first = False

	# internal page thru 404
	elif type == 'noSitemapMatch':
		print(color.RED + color.BOLD + "##vso[task.logissue type=warning]No page URL in the sitemap matches the URL path you've entered: " + color.END + URLPath)
		internalExitCode = 1
		first = False

	# internal link is constructed in an absolute manner which is suboptimal
	elif type == 'absorel':
		if beQuiet == False:
			print(color.YELLOW + color.BOLD + "##vso[task.logissue type=warning] WARNING: relative link with absolute URL: " + color.END + ln)
			first = False

	# link looks like internal but we didn't download it (wasn't in sitemap?)
	elif type == 'unreachable':
		if beQuiet == False:
			print(color.YELLOW + color.BOLD + "##vso[task.logissue type=warning] Can't check anchor validity:" + color.END + " the target page not in current DB (probably wasn't in the sitemap). Link: " + redir)
			first = False

	# outside link isn't in DB and the --no-external switch is True so we can't fetch it to check it
	elif type == 'cantGoOutside':
		if beQuiet == False:
			print(color.YELLOW + color.BOLD + "##vso[task.logissue type=warning] Can't check anchor validity:" + color.END + " the target page not in current DB and you forbade me to probe pages outside domain + folder (-x switch). Link: " + ln)
			first = False

	# Github line hilighting anchor is not OK (probably points to a line number that's not in the code)
	elif type == 'GHLineHilight':
		if beQuiet == False:
			# Any anchors on GitHub are a problem because GH uses JS to navigate to the right place, not the standard HTML ways -> commenting this out.
			# print(color.YELLOW + color.BOLD + "##vso[task.logissue type=warning] GitHub line highlight refers to line(s) nonexistent in the code: " + color.END + ln)
			first = False

	# External broken anchor, we're treating it as a warning only
	elif type == "externalNOK":
		if beQuiet == False:
			print(color.YELLOW + color.BOLD + "##vso[task.logissue type=warning] External anchor doesn't seem to exist: " + color.END + ln)
			first = False

	# External link either didn't resolve on DNS level, or timed out.
	elif type == "normalLinkUnreachable":
		print(color.RED + color.BOLD + "##vso[task.logissue type=error] Link unreachable (HTTP code " + str(errorCode) + "): " + color.END + ln)
		first = False

	# External link either didn't resolve on DNS level, or timed out.
	elif type == "normalLinkUnresolved":
		print(color.YELLOW + color.BOLD + "##vso[task.logissue type=warning] URL resolution or time-out error. Manual check advised (HTTP code " + str(errorCode) + "): " + color.END + ln)
		first = False

	# we can positively say the ID (anchor) isn't in the target page
	else:
		print(color.RED + color.BOLD + "##vso[task.logissue type=error] Anchor NOK: " + color.END + ln)
		internalExitCode = 1
		first = False

	exitCode = internalExitCode
	return first

# Set up some counters first so we can print stats when done.
okInternal = 0
okInPage = 0
nokInternal = 0
nokInPage = 0
missed = 0
notInSitemap = 0
okAnchorOutside = 0
nokAnchorOutside = 0
okNormalLinks = 0
unreachable = 0
pagesChecked = 0
retrieved = 0
absorel = 0
checkedLinks = {}

def printStats():
	print(color.BOLD + "\n===== STATS ===== " + color.END + \
	      " \nTotal pages checked: " + str(pagesChecked) + \
	      "\nAnchor links: " + \
	      "\n\tOK - in-page: " + str(okInPage) + \
	      "\n\tOK - internal: " + str(okInternal) + \
	      "\n\tNOK - in-page: " + str(nokInPage) + \
	      "\n\tNOK - internal: " + str(nokInternal) + \
	      "\n\tOK outside portal: " + str(okAnchorOutside) + \
	      "\n\tNOK outside portal: " + str(nokAnchorOutside) + \
	      "\nOK - normal links: " + str(okNormalLinks) + " (" + str(len(checkedLinks)) + " unique)" \
	      "\nUnreachable links: " + str(unreachable) + \
	      "\nAbsolute URLs within Domain: " + str(absorel) + \
	      "\nPages not in sitemap: " + str(notInSitemap) + \
	      "\n\nScript execution time: " + str(round(time.time() - startTime)) + " sec.")

def printDebugTime(message, blockStartTime, scriptStartTime):
	print(message + " " + str(round(time.time() - blockStartTime)) + " sec. (" + str(round(time.time() - scriptStartTime)) + " since start)")
	return time.time()

# Open locally saved sitemap
# sitemap=str(open("sitemap.xml", "r").read())

if beVerbose:
	debugTime = printDebugTime("Initialization took", startTime, startTime)

try:

	# Get the whole live sitemap, read the HTTP object and convert it to string. Requires import urllib.request
	# Tips for KL sitemap locations:
		# Preview: https://kcd-web-preview-master.azurewebsites.net/learn/sitemap.xml
		# Live: https://kontent.ai/learn/sitemap.xml
	if manualSitemapLoc:
		print("Getting the remote sitemap from manually selected location: " + manualSitemapLoc)
		try:
			sitemap = str(urllib.request.urlopen(manualSitemapLoc).read())
		except:
			firstError = printNOK("", manualSitemapLoc, True, "sitemapNotFound")
			sys.exit(exitCode)
	else:
		print("Getting the remote sitemap. Assuming it's at " + domain + folder + "/sitemap.xml\n") # (As it should according to https://www.sitemaps.org/protocol.html#location)")
		try:
			sitemap = str(urllib.request.urlopen(domain + folder + "/sitemap.xml").read())
		except:
			firstError = printNOK("", domain + folder + "/sitemap.xml", True, "sitemapNotFound")
			sys.exit(exitCode)

	if beVerbose:
		debugTime = printDebugTime("Getting the sitemap took", debugTime, startTime)

	# Find all URLs with the URLPath in the sitemap file. "rf" in findall means r=regex, f=allow variables in the string searched for. Regexes require import re.
	URLs = re.findall(rf'({URLPath}.*?)</loc>', sitemap)

	if beVerbose:
		debugTime = printDebugTime("Parsing the URLs in the sitemap took", debugTime, startTime)

	# Prepare dictionary where key will be a page title and value an array with links containing a hash character (ie. a link with an anchor)
	pagesLinksAndAnchors = {}

	# Go thru the URLs obtained from the sitemap and get anchor links and IDs so we can check them later.
	# Set up counter of retrieved pages so we can report progress to a user.
	wasAbsorel = {}
	total = len(URLs)
	for URL in URLs:
		retrieved += 1
		# get the page source
		try:
			# page = str(urllib.request.urlopen(URL).read())
			browser.get(URL)
			# Wait 6 seconds until atrocities like Management API v2 process all the JS
			if "reference" in URL:
				time.sleep(6)
			page = browser.page_source
		except:
			firstError = printNOK("", URL, firstError, "internalSitemap404")

		# get the page's <title>
		title = re.search(rf'<title>(.*?)</title>',page).group(1)

		# Each page will have its own nested dictionary with 'URL' as primary key and title' and 'anchorLinks' as nested keys
		pagesLinksAndAnchors[URL] = {}
		pagesLinksAndAnchors[URL]['title'] = title

		# Get links with anchors (hash followed by at least one character except for a closing quote) in the page and save them to the pagesLinksAndAnchors dict
		anchorLinks = re.findall(rf'href="([^"]*?#[^\"]+?)"',page)

		# Get non-anchor links (opening quotes followed by at least one character and the link doesn't contain a hash) in the page and safe them to the pagesLinksAndAnchors dict
		normalLinks = re.findall(rf'<a .*?href="([^"#]+?)"',page)

		# Assign the normal links to the main DB of pages w/ links inside them
		pagesLinksAndAnchors[URL]['normal-links'] = normalLinks

		# Cleaning up some anchor mess
		# Delete anchor links that are term definitions (start with "#term-definition-term_"). They're causing false positives since there's no heading with such ID (https://kentico.atlassian.net/browse/CTC-1009)
		# Also delete all links to app.diagrams.net and viewer.diagrams.net because they're wicked and cause false positives (they contain anchor character but they don't lead to any anchor in the target page)
		# Also #2 delete the "#main" and "#subscribe-breaking-changes-email" anchor links because they're just internal bullshitery in KL
		# Also #3 delete all GitHub links as GH apparently uses JS instead of the standard HTML way to navigate to the correct place
		# We can safely do this in one loop because the loop contains only one condition block and the i var will never get incremented unless nothing gets deleted.
		i = 0
		while i < len(anchorLinks):
			if re.match("#term-definition-term_", anchorLinks[i]):
				# delete the invalid anchor link; mutates the existing array
				del anchorLinks[i]
			elif re.match("https://app.diagrams.net", anchorLinks[i]):
				del anchorLinks[i]
			elif re.match("https://viewer.diagrams.net", anchorLinks[i]):
				del anchorLinks[i]
			elif re.match("https://github.com", anchorLinks[i]):
				del anchorLinks[i]
			elif re.match("#main", anchorLinks[i]):
				del anchorLinks[i]
			elif re.match("#subscribe-breaking-changes-email", anchorLinks[i]):
				del anchorLinks[i]
			else:
				i += 1

		i = 0
		while i < len(anchorLinks):

			# If the link is longer than 2048 characters, it's quite probably some weirdness like links to diagram.net that have the whole diagram encoded into the URL, apparently. Delete such links, the hash character there doesn't stand for an anchor link anyway.
			if len(anchorLinks[i]) > 2048:
				del anchorLinks[i]

			# This will be used to just warn user that they have relative link that's not implemented as relative (starts with the domain instead of just slash).
			if re.match(domain, anchorLinks[i]):
				if not URL in wasAbsorel:
					wasAbsorel[URL] = []
				wasAbsorel[URL].append(anchorLinks[i])
				absorel += 1

			# Replace the relative URL prefix with full URL
			# anchorLinks[i] = re.sub(rf'^{folder}', URLPath, anchorLinks[i])
			anchorLinks[i] = re.sub(rf'^/', domain + '/', anchorLinks[i])

			i += 1

		# Assign cleaned anchor links to the main DB of pages w/ links inside them
		pagesLinksAndAnchors[URL]['anchor-links'] = anchorLinks

		# Get HTML ID attributes in the page
		anchors = re.findall(rf'id="(.*?)"', page)
		pagesLinksAndAnchors[URL]['anchors'] = anchors

		# Progress reporting
		percentProgress = str(round((retrieved/total)*100, 2))

		# If the retrieving is done (on the last page, it's 100 % done so we don't want to overwrite the status line with a new updated one anymore). 1 = 100 %
		if retrieved/total == 1:
			end = "\n\n"
		else:
			end = "\r"

		# Commenting the progress reporting out because the it's messing up logs in Smoke Tests in Azure DevOps.
		# print("Retrieved and processed pages obtained from the sitemap: " + str(retrieved) + "/" + str(total) + " (" + percentProgress + " %)", end=end)

		if beVerbose:
			debugTime = printDebugTime("Getting the " + URL + " took", debugTime, startTime)

	if retrieved == 0:
		firstError = printNOK(type="noSitemapMatch")
		# print(color.RED + color.BOLD + "##vso[task.logissue type=warning]No page URL in the sitemap matches the URL path you've entered: " + URLPath + color.END)
		exitCode = 1

	# Now we go thru the anchor links we got and check whether the anchors exist.

	for page in pagesLinksAndAnchors:
		# This is indicator whether we're printing the 1st error for the current page. If yes, then print the page title and URL. If not, don't print that, just print the error.
		firstError = True
		# print("\nProcessing page " + color.BOLD + pagesLinksAndAnchors[page]['title'] + color.END)
		for link in pagesLinksAndAnchors[page]["anchor-links"]:

			# Inform user the link is absolute even though it's within the domain
			try:
				if link in wasAbsorel[page]:
					# print("IF LINK IN ABSOREL: " + link)
					firstError = printNOK(page, link, firstError, "absorel")
			except:
				pass

			# If the link is an in-page anchor link
			if re.match(rf'#', link):
				if link.replace("#", "") in pagesLinksAndAnchors[page]["anchors"]:
					okInPage += 1
				else:
					firstError = printNOK(page, link, firstError)
					nokInPage += 1

			# If the link is anchor link to another page inside the portal
			elif re.match(rf'{URLPath}', link):
				linkBaseURL = re.search(fr'(.*?)#', link).group(1)
				linkAnchor = re.search(fr'#(.*)', link).group(1)
				if linkBaseURL in pagesLinksAndAnchors:
					if linkAnchor in pagesLinksAndAnchors[linkBaseURL]['anchors']:
						okInternal += 1

					else:
						firstError = printNOK(page, link, firstError)
						nokInternal += 1
				else:
					# See if it isn't just a redirect - requests.get() gets history with return HTTP codes, .url contains the final landing URL. Requires import requests
					# redirection = ""
					# print("baseURL: " + linkBaseURL)
					finalURL = requests.get(linkBaseURL).url
					# print("finalURL: " + finalURL)
					# print("link: " + link)

					# removed printing of the redirection info bcs it's redundant
					# if finalURL != linkBaseURL:
						# redirection = " ===> " + finalURL

					# Repeating the checking code here but I'm too lazy now;; See if the final URL is in the URLs we have already.
					if finalURL in pagesLinksAndAnchors:
						if linkAnchor in pagesLinksAndAnchors[finalURL]['anchors']:
							okInternal += 1
						else:
							# printNOK(page, link, firstError, None, redirection)
							firstError = printNOK(page, link, firstError, None, finalURL)
							nokInternal += 1
					# This is a legacy branch and it should never occur. If it does, it means that the page is in our (sub)portal (domain + folder) but it wasn't in the sitemap. Leaving this here because it might prove to be a good way to check for incomplete sitemap. Should this be unwanted, then this branch needs to redirect to the branch which gets outside page to check it.
					else:
						# printNOK(page, link, firstError, "unreachable", redirection)
						firstError = printNOK(page, link, firstError, "unreachable", finalURL)
						notInSitemap += 1

			# The link leads outside the (sub)portal, let's download them and see if the anchor exists in the target page (but only if user didn't prohibit this by the -x switch)
			else:
				if noExternal == False:
					# The try/except structure is here to test whether the page exists (the potential 404 kills the whole script by Python throwing an exception).
					try:
						# if the link seems to be relative (doesn't start with 'http' but with '/' so it leads to the domain but not to the domain+folder path), so let's add the domain to it.
						if re.match(r'^/', link):
							link = domain + link

						# Build the request for the outside page. Since some sites apparently don't like the Python3's URLlib user agent (e.g. diagrams.net), we need to set it to something they'll like (hence the headers={...} part.
						# req = urllib.request.Request(link, headers={'User-Agent': 'Mozilla/5.0'})

						# Get the outside page
						# outsidePage = str(urllib.request.urlopen(req).read())
						browser.get(link)
						# time.sleep(4)
						outsidePage = browser.page_source

						# Get base URL and anchor from the link
						outsideLinkBaseURL = re.search(r'(.*?)#', link).group(1)
						outsideLinkAnchor = re.search(r'#(.*)', link).group(1)
						
						# First try the normal anchor system - anchors go to IDs in the page
						if re.search(rf'id="{outsideLinkAnchor}"', outsidePage):
							okAnchorOutside += 1

						# Delete the GitHub workaround, we're not using it anyway
						# If that fails, it can also be GitHub's bullshitery - they don't give <hX> tags IDs but put an <a class="anchor" href="#anchor"...> links inside them with the href="#anchor" in lowercase (hence the , re.IGNORECASE) and use JavaScript to scroll down to the link. So let's search for that before we give up entirely and say the anchor is bad. This is fragile, BTW - if they change the structure of the link, this test will fail.
						elif re.search(rf'class="anchor".*?href="#{outsideLinkAnchor}', outsidePage, re.IGNORECASE):
							okAnchorOutside += 1

						elif re.search(rf'#L\d+(-L\d+)?', link):
							# We split the potential lines range to two items bcs the whole anchor isn't in the page source - we need to search for bounderies of the highlight (e.g. #L80-L86 will be both IDs to check)
							hilightRange = outsideLinkAnchor.split("-")
							line = 0
							while line < len(hilightRange):
								if re.search(rf'id="{hilightRange[line]}"', outsidePage):
									GHhilight = "OK"
								else:
									GHhilight = "NOK"
								line += 1
							if GHhilight == "NOK":
								nokAnchorOutside += 1
								firstError = printNOK(page, link, firstError, "GHLineHilight")
							else:
								okAnchorOutside += 1

						# Tried everything, the anchor is either some 3rd party atrocity or broken (but it's external so we don't treat it as an error just because of those 3rd-party bullshiteries)
						else:
							firstError = printNOK(page, link, firstError, "externalNOK")
							nokAnchorOutside += 1
					# Apparently the page doesn't exist (other possible issues can be 403, 500 or other error codes, we don't really care what exactly it is)
					except:
						firstError = printNOK(page, link, firstError, "404")
						unreachable += 1
				else:
					firstError = printNOK(page, link, firstError, "cantGoOutside")
		# print("unreachable: " + str(unreachable))
		if beVerbose:
			debugTime = printDebugTime("Processing anchor links for " + page + " took", debugTime, startTime)

		# According to the docs, using sessions can significantly improve performance -- "if you’re making several requests to the same host, the underlying TCP connection will be reused"
		# https://requests.readthedocs.io/en/latest/user/advanced/#session-objects
		# Potentially useful for setting up retry policy: https://stackoverflow.com/a/47475019/2216968 (from requests.adapters import HTTPAdapter and from urllib3.util.retry import Retry)
		sessionForRequests = requests.Session()

		# Add an accepted user agent to the Sessions so certain pages (like prerender.io) don't block the requests with 403 or close the connection without a response altogether:
		# sessionForRequests.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:12.0) Gecko/20100101 Firefox/12.0'})
		sessionForRequests.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'})

		for link in pagesLinksAndAnchors[page]["normal-links"]:
			# If the link is relative, add the domain to it to make it absolute including the protocol.
			if re.match(r'^/', link):
				link = domain + link

			# Avoid loading the same links again and again (headers, navigation, footers, ...)
			if link in checkedLinks:
				if checkedLinks[link]['status'] == "OK":
					okNormalLinks += 1
				else:
					firstError = printNOK(page, link, firstError, "normalLinkUnreachable", "", checkedLinks[link]['code'])
					unreachable += 1

			else:
				# Remove some links from the testing (e.g., fonts, localhosts, example domains, and codepen which blocks Requests entirely with 403)
				# 	Zapier.com is OK with headless Firefox but refuses requests library
				#	Cloudflare refuses everything, possible solution is another webdriver: https://stackoverflow.com/questions/68289474/selenium-headless-how-to-bypass-cloudflare-detection-using-selenium
				#	'%7B' is URL-encoded curly bracket '{' -- used in example URLs to encapsulate variables ('{var}')
				if not (re.search(r'woff2?$', link) \
				        or re.match('blob:https://kontent.ai', link) \
				        or re.match('https://assets-us-01.kc-usercontent.com', link) \
				        or re.match('https://player.vimeo.com/video/', link) \
				        or re.match('mailto:', link) \
				        or re.match(r'https?://127.0.0.1', link) \
				        or re.match(r'https?://deliver.kontent.ai', link) \
				        or re.match(r'https?://localhost', link) \
				        or re.match(r'https?://manage.kontent.ai', link) \
				        or re.match(r'https?://preview-graphql.kontent.ai', link) \
				        or re.search('%7B', link) \
				        or re.search('cloudflare.com', link) \
				        or re.search('codepen.io', link) \
				        or re.search('example.com', link) \
				        or re.search('example.org', link) \
				        or re.search('file-name', link) \
				        or re.search('file_name', link) \
				        or re.search('filename', link) \
				        or re.search('zapier.com', link) \
				        or re.search(r'learn/pdf/\?url', link) \
				       ):
					checkedLinks[link] = {}
					try:
						req = sessionForRequests.get(link, timeout=5)
						if req.status_code > 399:
							checkedLinks[link]['status'] = "NOK"
							checkedLinks[link]['code'] = req.status_code
							firstError = printNOK(page, link, firstError, "normalLinkUnreachable", "", req.status_code)
							unreachable += 1
						else:
							checkedLinks[link]['status'] = "OK"
							checkedLinks[link]['code'] = req.status_code
							okNormalLinks += 1
					except:
						checkedLinks[link]['status'] = "NOK"
						checkedLinks[link]['code'] = "unknown"
						firstError = printNOK(page, link, firstError, "normalLinkUnresolved", "", "unknown") # we can't print req.status_code here because it a value from the previous successful try block.
						unreachable += 1

			# print("unreachable: " + str(unreachable))

		if beVerbose:
			debugTime = printDebugTime("Processing normal links for " + page + " took", debugTime, startTime)		

		# Counter of the number of checked pages
		pagesChecked += 1

	# Finished, close temporary headless Firefox and print statistics
	printStats()
	browser.quit()

	# TODO -- tohle vratit pred nasazenim do Azure
	# try:
	#	line = os.popen('tasklist /v').read().strip().split('\n')
	#     name  = "geckodriver.exe"
	#     for i in range(len(r)):
	#         if name in line[i]:
	#             os.system("taskkill /im %s /f" %(name))
	#             print("Process Successfully terminated")
	  
	# except: 
	# 	print("Error Encountered while running script") 
	sys.exit(exitCode)

except Exception:
	print("Error occured or interuption code (^C) caught, terminating now.")
	exitCode = 1
	printStats()
	browser.quit()
	print("The exception:")
	traceback.print_exc()
	sys.exit(exitCode)



