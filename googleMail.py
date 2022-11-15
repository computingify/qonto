# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START gmail_quickstart]
from __future__ import print_function
from os import stat

import os.path

from google.auth.transport.requests import Request # pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
import sys
import datetime

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def gmailAuthenticate():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def search_messages(service, query):
    result = service.users().messages().list(userId="me", q=query).execute()
    messages = []
    if "messages" in result:
        messages.extend(result["messages"])
    while "nextPageToken" in result:
        page_token = result["nextPageToken"]
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token)
            .execute()
        )
        if "messages" in result:
            messages.extend(result["messages"])
    return messages


def get_size_format(b, factor=1024, suffix="B"):
    """
    Scale bytes to its proper byte format
    e.g:
        1253656 => '1.20MB'
        1253656678 => '1.17GB'
    """
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if b < factor:
            return f"{b:.2f}{unit}{suffix}"
        b /= factor
    return f"{b:.2f}Y{suffix}"


def clean(text):
    # clean text for creating a folder
    return "".join(c if c.isalnum() else "_" for c in text)


def parse_parts(service, parts, folder_name, message):
    """
    Utility function that parses the content of an email partition
    """
    # print("in parse", parts)
    if parts:
        for part in parts:
            filename = part.get("filename")
            mimeType = part.get("mimeType")
            body = part.get("body")
            data = body.get("data")
            file_size = body.get("size")
            part_headers = part.get("headers")
            if part.get("parts"):
                # recursively call this function when we see that a part
                # has parts inside
                parse_parts(service, part.get("parts"), folder_name, message)
            if mimeType == "text/plain":
                # if the email part is text plain
                if data:
                    text = urlsafe_b64decode(data).decode()
                    # print(text)
            elif mimeType == "text/html":
                # if the email part is an HTML content
                # save the HTML file and optionally open it in the browser
                if not filename:
                    filename = "index.html"
                filepath = os.path.join(folder_name, filename)
                print("Saving HTML to", filepath)
                with open(filepath, "wb") as f:
                    f.write(urlsafe_b64decode(data))
            else:
                # attachment other than a plain text or HTML
                for part_header in part_headers:
                    part_header_name = part_header.get("name")
                    part_header_value = part_header.get("value")
                    if part_header_name == "Content-Disposition":
                        if "attachment" in part_header_value:
                            # we get the attachment ID
                            # and make another request to get the attachment itself
                            print(
                                "Saving the file:",
                                filename,
                                "size:",
                                get_size_format(file_size),
                            )
                            attachment_id = body.get("attachmentId")
                            attachment = (
                                service.users()
                                .messages()
                                .attachments()
                                .get(
                                    id=attachment_id,
                                    userId="me",
                                    messageId=message["id"],
                                )
                                .execute()
                            )
                            data = attachment.get("data")
                            filepath = os.path.join(folder_name, filename)
                            if data:
                                with open(filepath, "wb") as f:
                                    f.write(urlsafe_b64decode(data))


def read_message(service, message, isSaveInDirectory):
    """
    This function takes Gmail API `service` and the given `message_id` and does the following:
        - Downloads the content of the email
        - Prints email basic information (To, From, Subject & Date) and plain/text parts
        - Creates a folder for each email based on the subject
        - Downloads text/html content (if available) and saves it under the folder created as index.html
        - Downloads any file that is attached to the email and saves it in the folder created
    """
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message["id"], format="full")
        .execute()
    )
    # print(json.dumps(msg, indent=2))

    # parts can be the message body, or attachments
    payload = msg["payload"]
    headers = payload.get("headers")
    parts = payload.get("parts")
    folder_name = "email"
    has_subject = False
    if headers:
        # this section prints email basic info & creates a folder for the email
        for header in headers:
            name = header.get("name")
            value = header.get("value")
            if name.lower() == "from":
                # we print the From address
                print("From:", value)
            if name.lower() == "to":
                # we print the To address
                print("To:", value)
            if name.lower() == "subject":
                # make our boolean True, the email has "subject"
                has_subject = True
                # make a directory with the name of the subject
                folder_name = clean(value)
                # we will also handle emails with the same subject name
                folder_counter = 0
                while os.path.isdir(folder_name):
                    folder_counter += 1
                    # we have the same folder name, add a number next to it
                    if folder_name[-1].isdigit() and folder_name[-2] == "_":
                        folder_name = f"{folder_name[:-2]}_{folder_counter}"
                    elif folder_name[-2:].isdigit() and folder_name[-3] == "_":
                        folder_name = f"{folder_name[:-3]}_{folder_counter}"
                    else:
                        folder_name = f"{folder_name}_{folder_counter}"
                os.mkdir(folder_name)
                print("Subject:", value)
            if name.lower() == "date":
                # we print the date when the message was sent
                print("Date:", value)
    if not has_subject and isSaveInDirectory:
        # if the email does not have a subject, then make a folder with "email" name
        # since folders are created based on subjects
        if not os.path.isdir(folder_name):
            os.mkdir(folder_name)

    if parts:
        if isSaveInDirectory:
            parse_parts(service, parts, folder_name, message)

    print("=" * 50)

    return folder_name