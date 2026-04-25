from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.http import HttpResponse 
from django.contrib import auth
import datetime
import os
import sys
from pathlib import Path
import boto3
import re
import json
from openai import OpenAI

#Seeing if I can edit
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

#Import vitalib
sys.path.insert(0, str(BASE_DIR.parent))
import vitalib

def logged_in_header():
    with open(os.path.join(BASE_DIR,"templates/sub_templates/logged_in_header.html"),"r") as f:
        return f.read()

def not_logged_in_header():
    with open(os.path.join(BASE_DIR,"templates/sub_templates/not_logged_in_header.html"),"r") as f:
        return f.read()

def home(request):
    #Check if user is logged in
    if request.user.is_authenticated:
        db_connection = vitalib.db.connection.open()
        points = vitalib.db.user_info.get(db_connection,request.user.username).points()
        flashcard_count = vitalib.db.vocabulary.count(db_connection,request.user.username).today()
        last_article = vitalib.db.user_info.get(db_connection,request.user.username).last_article_read()
        vitalib.db.connection.close(db_connection)
        return render(request,'dashboard.html',{
            "header":logged_in_header(), 
            "user":request.user, 
            "article_read":datetime.datetime.now().date() == last_article, 
            "points":points, 
            "flashcard_count":flashcard_count})
    else:
        return HttpResponseRedirect("/login/")
    
def account(request):
    #Check if user is logged in
    if request.user.is_authenticated:
        #Get language and points from the database
        db_connection = vitalib.db.connection.open()
        language_code = vitalib.db.user_info.get(db_connection,request.user.username).language()
        language = vitalib.transform.language(language_code).code_to_name()
        points = vitalib.db.user_info.get(db_connection,request.user.username).points()
        vitalib.db.connection.close(db_connection)
        return render(request,'account.html',{"header":logged_in_header(), "user":request.user, "language":language, "points":points})
    else:
        return HttpResponseRedirect("/login/")
    
def daily_article(request):
    #Check if user is logged in
    if request.user.is_authenticated:
        #Open the database connection
        db_connection = vitalib.db.connection.open()
        #If the user's last article read is today ridirect to the home page
        last_article = vitalib.db.user_info.get(db_connection,request.user.username).last_article_read()
        if datetime.datetime.now().date() == last_article:
            vitalib.db.connection.close(db_connection)
            return HttpResponseRedirect("/")
        #Get the user's language
        language_code = vitalib.db.user_info.get(db_connection,request.user.username).language()
        #The filename we need is the current date in the format YYYY-MM-DD.json
        filename = str(datetime.datetime.now().date())+".json"
        #Create S3 Session
        #The AWS access key is an environment variable called AWS_ACCESS
        #The AWS secret key is an environment variable called AWS_SECRET
        #The AWS region is an environment variable called AWS_REGION
        aws_access_key_id = os.environ['AWS_ACCESS']
        aws_secret_access_key = os.environ['AWS_SECRET']
        aws_region = os.environ['AWS_REGION']
        my_session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )
        #Download the article from the bucket called evenstarsec.vitamova
        s3 = my_session.resource('s3')
        #The article is in the folder articles/language
        #The filename is the current date in the format YYYY-MM-DD.json
        obj = s3.Object('evenstarsec.vitamova', 'articles/'+language_code+'/'+filename)
        article = eval(obj.get()['Body'].read())
        #Make a list of tags for each paragraph named p1, p2, p3, etc.
        paragraphs = []
        s_index = 1
        w_index = 1
        #Create a word to sentence index
        w2s_map = []
        for i in range(len(article["text"])):
            #I want to add a span tag with ids s1, s2, s3, etc. for each sentence
            #I want to add a span tag with ids w1, w2, w3, etc. for each word
            #Sentences are separated by periods, question marks, and exclamation points followed by a space, single quote, or double
            sentence_regex = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)(?=\s|'|\")"
            sentences = re.split(sentence_regex,article["text"][i])
            for j in range(len(sentences)):
                words = sentences[j].split(" ")
                for k in range(len(words)):
                    w2s_map.append({"word":"w"+str(w_index),"sentence":"s"+str(s_index)})
                    words[k] = "<span id='w"+str(w_index)+"'>"+words[k]+"</span>"
                    w_index += 1
                sentences[j] = " ".join(words)
                sentences[j] = "<span id='s"+str(s_index)+"'>"+sentences[j]+"</span>"
                s_index += 1
            article["text"][i] = " ".join(sentences)
            paragraphs.append({"tag":"p"+str(i+1),"text":article["text"][i]})
        #Iterate through the questions and add an index to each question
        for i in range(len(article["questions"])):
            article["questions"][i]["index"] = i+1
        #Return the article title and the text as a list of paragraphs
        if request.method == 'POST':
            #Get the correct answers from the article
            correct_answers = []
            for question in article["questions"]:
                #Strop the correct answer of white space and make it an integer
                correct_answers.append(int(question["correct_answer"].strip()))
            #Compare the correct answers to the user's answers
            user_answers = json.loads(request.body)["answers"]
            total_correct = 0
            for i in range(len(user_answers)):
                if user_answers[i] == correct_answers[i]:
                    #Add one point to the user
                    vitalib.db.user_info.update(db_connection,request.user.username).points(2)
                    total_correct += 1
            #Add 10 points to the user
            vitalib.db.user_info.update(db_connection,request.user.username).points(10)
            #Make the user's last article read the current date
            vitalib.db.user_info.update(db_connection,request.user.username).last_article_read(str(datetime.datetime.now().date()))
            vitalib.db.connection.close(db_connection)
            return HttpResponse(
                json.dumps({
                    "correct_answers": correct_answers, 
                    "total_correct": total_correct
                }), content_type="application/json")
        elif request.method == 'GET':
            vitalib.db.connection.close(db_connection)
            return render(request,'daily_article.html',{
                "title":article["title"],
                "paragraphs":paragraphs,
                "header":logged_in_header(),
                "w2s_map":w2s_map, 
                "questions":article["questions"] 
                })
        else:
            #Return error
            return HttpResponse("Error: Invalid request method", content_type="text/plain")
    else:
        return HttpResponseRedirect("/login/")
    
def flashcards(request):
    #Check if user is logged in
    if request.user.is_authenticated:
        #If request is GET
        if request.method == 'GET':
            db_connection = vitalib.db.connection.open()
            #Get the flashcard count for today
            flashcard_count = vitalib.db.vocabulary.count(db_connection,request.user.username).today()
            #If the flashcard count is zero, redirect to the home page
            if flashcard_count == 0:
                vitalib.db.connection.close(db_connection)
                return HttpResponseRedirect("/")
            else:
                #See if the get request has a query parameter called "q"
                if "q" in request.GET:
                    #q should be a number
                    try:
                        q = int(request.GET["q"])
                    except:
                        #If q is not a number, set q the flashcard count
                        q = flashcard_count
                else:
                    #If there is no q parameter, set q to the flashcard count
                    q = flashcard_count
                #Get the flashcards for today
                flashcards = vitalib.db.vocabulary.get(db_connection,request.user.username).today(q)
                vitalib.db.connection.close(db_connection)
                return render(request,'flashcards.html',{"header":logged_in_header(),"flashcards":json.dumps(flashcards)})
        elif request.method == 'POST':
            #Get the request json data
            jsondata = json.loads(request.body)
            db_connection = vitalib.db.connection.open()
            #If the word is correct, correct will be true in the data
            #If the word is incorrect, correct will be false in the data
            if jsondata["correct"]:
                #Use the level.increase method from the vocabulary class in the db module
                vitalib.db.vocabulary.level(db_connection,request.user.username).increase(jsondata["word_id"])
            elif not jsondata["correct"]:
                #Use the level.reset method from the vocabulary class in the db module
                vitalib.db.vocabulary.level(db_connection,request.user.username).reset(jsondata["word_id"])
            #Add one point to the user
            vitalib.db.user_info.update(db_connection,request.user.username).points(1)
            #Close the database connection
            vitalib.db.connection.close(db_connection)
            #Return text like "word + word_id + successfully updated"
            response = "Word " + str(jsondata["word_id"]) + " successfully updated"
            return HttpResponse(response, content_type="text/plain")
    else:
        return HttpResponseRedirect("/login/")

def submit_vocabulary(request):
    #Check if user is logged in
    if request.user.is_authenticated:
        #Get the request json data
        jsondata = json.loads(request.body)
        if len(jsondata) == 0:
            return HttpResponse("Error: No data provided", content_type="text/plain")
        else:
            base_text = """
                Please provide your responses in the 4 line format below. 
                Please do not write anything else so that I can parse this. 
                I am giving you Spanishs word and the sentences they were used in. 
                Please rewrite the word, tell me its base form, its translation in English, 
                and an example sentence which uses the same meaning of the word but in at least a slightly different context. 
                If multiple translations of the word are relevant to the sentence, you can provide the multiple translations separated by a comma.
                The translation must be of the base form of the verb.
                Please do not put more than 3 translations per word. If AND ONLY IF the word is a verb is used reflexively, 
                please treat the base form as its reflexive form and make the translation for the reflexive verb. 
                Please seperate your responses per word by a single line. Please only provide one response per word/sentence pair below. 
                If the word is the base form, please rewrite the word as the base form. Do NOT write the base form as none. 
                If the word is the reflexive form, please rewrite the word as the reflexive form.
                Please make sure you include the words before the : symbol in your response. I am using these to parse the data.
                Word: 
                Base form: 
                Translation:
                Example sentence:
                Example translation:        
            """
            added_text = ""
            response_text = ""
            condition = True
            attempt = 1
            while condition:
                for i in range(len(jsondata)):
                    added_text += "Word: "+jsondata[i]["word"]+"\n"
                    added_text += "Sentence: "+jsondata[i]["sentence"]+"\n"
                    model = "gpt-3.5-turbo"
                    #Check if user is in the "pro" group
                    if request.user.groups.filter(name="pro").exists():
                        #Then they can use the gpt-4o model
                        print("User is in the pro group")
                        model = "gpt-4o"
                    if len(base_text) + len(added_text) > 10000 or i == len(jsondata)-1:
                        # Use the new ChatCompletion.create method
                        client = OpenAI(
                            # This is the default and can be omitted
                            api_key=os.environ.get('CHATGPT_KEY'),
                        )

                        response = client.chat.completions.create(
                            messages=[
                                {
                                    "role": "user",
                                    "content": base_text+added_text,
                                }
                            ],
                            model=model,
                        )
                        print(response)
                        #Parse the response
                        response_text += response.choices[0].message.content
                        #Reset the added text
                        added_text = ""
                #Split the response by line
                response_lines = response_text.split("\n")
                #Create a dictionary to hold the words and their data
                words = []
                for i in range(len(response_lines)):
                    if response_lines[i][0:6] == "Word: ":
                        word_dict = {"word": response_lines[i][6:].strip()}
                    elif response_lines[i][0:11] == "Base form: ":
                        word_dict["base"] = response_lines[i][11:].strip()
                    elif response_lines[i][0:13] == "Translation: ":
                        word_dict["translation"] = response_lines[i][13:].strip()
                    elif response_lines[i][0:17] == "Example sentence:":
                        word_dict["example"] = response_lines[i][17:].strip()
                    elif response_lines[i][0:20] == "Example translation:":
                        word_dict["example_translation"] = response_lines[i][20:].strip()
                        words.append(word_dict)
                #If the words are not empty, break the loop
                if len(words) > 0:
                    condition = False
                elif attempt > 3:
                    #If the attempt is greater than 3, return an error
                    return HttpResponse("Error: Failed to parse the data", content_type="text/plain")
                else:
                    #Add to the base text asking to please use the 4 line format properly
                    base_text += """
                    Please use the 4 line format properly. Please do not forget to include the words before the : symbol in your response. 
                    I am using these to parse the data. This is attempt number """+str(attempt)+"."
                    attempt += 1
            #Add the words to the database
            db_connection = vitalib.db.connection.open()
            for word in words:
                vitalib.db.vocabulary.add(conn=db_connection, username=request.user.username, word=word["base"], definition=word["translation"], example=word["example"])
            vitalib.db.connection.close(db_connection)
            return HttpResponse(json.dumps(words), content_type="application/json")
    else:
        return HttpResponseRedirect("/login/")
    
def poetry(request):
    #Check if user is logged in
    if request.user.is_authenticated:
        return render(request,'poetry.html',{"header":logged_in_header()})
    else:
        return HttpResponseRedirect("/login/")