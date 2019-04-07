#!/usr/bin/env python3

import re
import sys
import requests
import argparse
import concurrent.futures
import json
from urllib.parse import unquote

from core.prompt import prompt
from core.requester import requester
from core.colors import red, green, white, end, info, bad, good, run
from core.utils import e, d, stabilize, random_string, slicer, joiner, unity_extracter, get_params, flatten_params, remove_tags


def quick_bruter(params, originalResponse, originalCode, factors, include, delay, headers, url, GET):
    newResponse = requester(url, joiner(params, include), headers, GET, delay)
    if newResponse.status_code != originalCode:
        return params
    elif not factors['sameHTML'] and len(newResponse.text) != (len(originalResponse)):
        return params
    elif not factors['samePlainText'] and len(remove_tags(originalResponse)) != len(remove_tags(newResponse.text)):
        return params
    else:
        return False

def bruter(param, originalResponse, originalCode, factors, include, reflections, delay, headers, url, GET):
    fuzz = random_string(6)
    data = {param : fuzz}
    data.update(include)
    response = requester(url, data, headers, GET, delay)
    newReflections = response.text.count(fuzz)
    reason = False
    if response.status_code != originalCode:
        reason = 'Different response code'
    elif reflections != newReflections:
        reason = 'Different number of reflections'
    elif not factors['sameHTML'] and len(response.text) != (len(originalResponse)):
        reason = 'Different content length'
    elif not factors['samePlainText'] and len(remove_tags(response.text)) != (len(remove_tags(originalResponse))):
        reason = 'Different plain-text content length'
    if reason:
        return {param : reason}
    else:
        return None


def narrower(oldParamList):
    newParamList = []
    potenialParameters = 0
    threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=threadCount)
    futures = (threadpool.submit(quick_bruter, part, originalResponse, originalCode, factors, include, delay, headers, url, GET) for part in oldParamList)
    for i, result in enumerate(concurrent.futures.as_completed(futures)):
        if result.result():
            potenialParameters += 1
            newParamList.extend(slicer(result.result()))
        print('%s Processing: %i/%-6i' % (info, i + 1, len(oldParamList)), end='\r')
    return newParamList


def heuristic(response, paramList):
    done = []
    forms = re.findall(r'(?i)(?s)<form.*?</form.*?>', response)
    for form in forms:
        method = re.search(r'(?i)method=[\'"](.*?)[\'"]', form)
        inputs = re.findall(r'(?i)(?s)<input.*?>', response)
        for inp in inputs:
            inpName = re.search(r'(?i)name=[\'"](.*?)[\'"]', inp)
            if inpName:
                inpType = re.search(r'(?i)type=[\'"](.*?)[\'"]', inp)
                inpValue = re.search(r'(?i)value=[\'"](.*?)[\'"]', inp)
                inpName = d(e(inpName.group(1)))
                if inpName not in done:
                    if inpName in paramList:
                        paramList.remove(inpName)
                    done.append(inpName)
                    paramList.insert(0, inpName)
                    print ('%s Heuristic found a potential parameter: %s%s%s' % (good, green, inpName, end))
                    print ('%s Prioritizing it' % good)


def extract_headers(headers):
    sortedHeaders = {}
    matches = re.findall(r'(.*):\s(.*)', headers)
    for match in matches:
        header = match[0]
        value = match[1]
        try:
            if value[-1] == ',':
                value = value[:-1]
            sortedHeaders[header] = value
        except IndexError:
            pass
    return sortedHeaders

def main():
    print ('''%s        _
       /_| _ '    
      (  |/ /(//) %sv1.3%s
          _/      %s''' % (green, white, green, end))


    parser = argparse.ArgumentParser() #defines the parser
    #Arguments that can be supplied
    parser.add_argument('-u', help='target url', dest='url', required=True)
    parser.add_argument('-d', help='request delay', dest='delay', type=int)
    parser.add_argument('-t', help='number of threads', dest='threads', type=int)
    parser.add_argument('-f', help='file path', dest='file')
    parser.add_argument('-o', help='Path for the output file', dest='output_file')
    parser.add_argument('--get', help='use get method', dest='GET', action='store_true')
    parser.add_argument('--post', help='use post method', dest='POST', action='store_true')
    parser.add_argument('--headers', help='http headers prompt', dest='headers', action='store_true')
    parser.add_argument('--include', help='include this data in every request', dest='include')
    args = parser.parse_args() #arguments to be parsed

    url = args.url
    params_file = args.file or './db/params.txt'
    headers = args.headers
    delay = args.delay or 0
    include = args.include or {}
    threadCount = args.threads or 2

    if headers:
        headers = extract_headers(prompt())
    else:
        headers = {}

    if args.GET:
        GET = True
    else:
        GET = False

    include = get_params(include)

    paramList = []
    try:
        with open(params_file, 'r') as params_file:
            for line in params_file:
                paramList.append(line.strip('\n'))
    except FileNotFoundError:
        print ('%s The specified file doesn\'t exist' % bad)
        quit()

    url = stabilize(url)

    print ('%s Analysing the content of the webpage' % run)
    firstResponse = requester(url, include, headers, GET, delay)

    print ('%s Now lets see how target deals with a non-existent parameter' % run)

    originalFuzz = random_string(6)
    data = {originalFuzz : originalFuzz[::-1]}
    data.update(include)
    response = requester(url, data, headers, GET, delay)
    reflections = response.text.count(originalFuzz[::-1])
    print ('%s Reflections: %s%i%s' % (info, green, reflections, end))

    originalResponse = response.text
    originalCode = response.status_code
    print ('%s Response Code: %s%i%s' % (info, green, originalCode, end))

    newLength = len(response.text)
    plainText = remove_tags(originalResponse)
    plainTextLength = len(plainText)
    print ('%s Content Length: %s%i%s' % (info, green, newLength, end))
    print ('%s Plain-text Length: %s%i%s' % (info, green, plainTextLength, end))

    factors = {'sameHTML': False, 'samePlainText': False}
    if len(firstResponse.text) == len(originalResponse):
        factors['sameHTML'] = True
    elif len(remove_tags(firstResponse.text)) == len(plainText):
        factors['samePlainText'] = True

    print ('%s Parsing webpage for potential parameters' % run)
    heuristic(firstResponse.text, paramList)

    fuzz = random_string(8)
    data = {fuzz : fuzz[::-1]}
    data.update(include)

    print ('%s Performing heuristic level checks' % run)

    toBeChecked = slicer(paramList, 25)
    foundParams = []
    while True:
        toBeChecked = narrower(toBeChecked)
        toBeChecked = unity_extracter(toBeChecked, foundParams)
        if not toBeChecked:
            break

    if foundParams:
        print ('%s Heuristic found %i potential parameters.' % (info, len(foundParams)))
        paramList = foundParams

    finalResult = []
    jsonResult = []

    threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=threadCount)
    futures = (threadpool.submit(bruter, param, originalResponse, originalCode, factors, include, reflections, delay, headers, url, GET) for param in foundParams)
    for i, result in enumerate(concurrent.futures.as_completed(futures)):
        if result.result():
            finalResult.append(result.result())
        print('%s Progress: %i/%i' % (info, i + 1, len(paramList)), end='\r')
    print('%s Scan Completed' % info)
    for each in finalResult:
        for param, reason in each.items():
            print ('%s Valid parameter found: %s%s%s' % (good, green, param, end))
            print ('%s Reason: %s' % (info, reason))
            jsonResult.append({"param": param, "reason": reason})


    # Finally, export to json
    if args.output_file and jsonResult:
        print("Saving output to JSON file in %s" % args.output_file)
        with open(str(args.output_file), 'w') as json_output:
            json.dump({"results":jsonResult}, json_output, sort_keys=True, indent=4,)


if __name__ == "__main__":
    main()