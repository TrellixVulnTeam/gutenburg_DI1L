#!/usr/bin/env python
"""Gutenburg - A better way to consume the gutenberg book catalog"""
__version__ = '1.0.5'
# std
import requests
import os
import tarfile
import json
import sys
import re
import tempfile
import sqlite3
from requests.utils import requote_uri
from shutil import rmtree, copyfileobj

# silence space in url warning from rdflib
import logging
logging.disable(logging.WARNING)

# pip
import rdflib
from alive_progress import alive_bar

def book_path(_id: int, path: str):
    return path + "/cache/epub/{}/pg{}.rdf".format(_id, _id)

# returns an array of json objects or none on file failure
def rdf_to_jsld(_id: int, path: str):
    g = rdflib.Graph()
    _path = book_path(_id, path)
    if os.path.exists(_path):
        g.load(_path)
        return json.loads(g.serialize(format="json-ld").decode("utf-8"))
    else:
        return None

# returns an array of dicts {
# "url" : {string url},
# "modified" : {string date},
# "size" : {int bytes}
# }
def files(jsld):
    files = []

    for obj in jsld:
        if "@type" in obj and "file" in obj["@type"][0]:
            file = {
                "url": requote_uri(obj["@id"]),
                "modified": obj["http://purl.org/dc/terms/modified"][0]["@value"],
                "size": obj["http://purl.org/dc/terms/extent"][0]["@value"],
            }
            files.append(file)

    return files


# returns an array of dicts {
# "name" : {string name},
# "death" : {int year or null},
# "birth" : {int year or null},
# "aliases": [{string name}],
# "page" : {string url or null}
# }
def authors(jsld):
    agents = []

    for obj in jsld:
        if (
            "@type" in obj
            and "pgterms/ebook" in obj["@type"][0]
            and "http://purl.org/dc/terms/creator" in obj
        ):
            for agent in obj["http://purl.org/dc/terms/creator"]:
                agents.append(agent["@id"])

    creators = []

    for obj in jsld:
        for agent in agents:
            if agent in obj["@id"]:

                creator = {
                    "name": obj["http://www.gutenberg.org/2009/pgterms/name"][0][
                        "@value"
                    ],
                    "birth": None,
                    "death": None,
                    "aliases": [],
                    "page": None,
                }

                if "http://www.gutenberg.org/2009/pgterms/birthdate" in obj:
                    creator["birth"] = obj[
                        "http://www.gutenberg.org/2009/pgterms/birthdate"
                    ][0]["@value"]

                if "http://www.gutenberg.org/2009/pgterms/deathdate" in obj:
                    creator["death"] = obj[
                        "http://www.gutenberg.org/2009/pgterms/deathdate"
                    ][0]["@value"]

                if "http://www.gutenberg.org/2009/pgterms/alias" in obj:
                    for alias in obj["http://www.gutenberg.org/2009/pgterms/alias"]:
                        creator["aliases"].append(alias["@value"])

                if "http://www.gutenberg.org/2009/pgterms/webpage" in obj:
                    creator["page"] = obj[
                        "http://www.gutenberg.org/2009/pgterms/webpage"
                    ][0]["@id"]

                creators.append(creator)

    return creators


# returns int times downloaded
def downloads(jsld):
    count = None
    for obj in jsld:
        if "@type" in obj and "pgterms/ebook" in obj["@type"][0]:
            count = obj["http://www.gutenberg.org/2009/pgterms/downloads"][0]["@value"]
    return count


# returns string title
def title(jsld):
    name = None
    for obj in jsld:
        if "@type" in obj and "pgterms/ebook" in obj["@type"][0]:
            name = obj["http://purl.org/dc/terms/title"][0]["@value"]
    return name


# returns string date issued yyyy-mm-dd
def issued(jsld):
    date = None
    for obj in jsld:
        if "@type" in obj and "pgterms/ebook" in obj["@type"][0]:
            date = obj["http://purl.org/dc/terms/issued"][0]["@value"]
    return date


# returns string description or None
def description(jsld):
    _description = None
    for obj in jsld:
        if "@type" in obj and "pgterms/ebook" in obj["@type"][0]:
            if "http://purl.org/dc/terms/description" in obj:
                _description = obj["http://purl.org/dc/terms/description"][0]["@value"]

    return _description


# returns an array of [string category]
def categories(jsld):
    ids = []
    for obj in jsld:
        if (
            "@type" in obj
            and "pgterms/ebook" in obj["@type"][0]
            and "http://www.gutenberg.org/2009/pgterms/bookshelf" in obj
        ):
            for _id in obj["http://www.gutenberg.org/2009/pgterms/bookshelf"]:
                ids.append(_id["@id"])

    _categories = []

    for obj in jsld:
        for _id in ids:
            if _id in obj["@id"]:
                _categories.append(
                    obj["http://www.w3.org/1999/02/22-rdf-syntax-ns#value"][0]["@value"]
                )

    return _categories


# returns an array of [string subject]
def subjects(jsld):
    ids = []
    for obj in jsld:
        if (
            "@type" in obj
            and "pgterms/ebook" in obj["@type"][0]
            and "http://purl.org/dc/terms/subject" in obj
        ):
            for _id in obj["http://purl.org/dc/terms/subject"]:
                ids.append(_id["@id"])

    _subjects = []

    for obj in jsld:
        for _id in ids:
            if _id in obj["@id"]:
                _subjects.append(
                    obj["http://www.w3.org/1999/02/22-rdf-syntax-ns#value"][0]["@value"]
                )

    return _subjects


# returns an array of [string language]
def languages(jsld):
    ids = []
    for obj in jsld:
        if "@type" in obj and "pgterms/ebook" in obj["@type"][0]:
            for _id in obj["http://purl.org/dc/terms/language"]:
                ids.append(_id["@id"])

    _languages = []

    for obj in jsld:
        for _id in ids:
            if _id in obj["@id"]:
                _languages.append(
                    obj["http://www.w3.org/1999/02/22-rdf-syntax-ns#value"][0]["@value"]
                )

    return _languages


# returns a valid json file with all the book info
def get_book(_id: int, path: str):
    dump = rdf_to_jsld(_id, path)

    if dump != None:
        _book = {
            "id": _id,
            "title": title(dump),
            "description": description(dump),
            "issued": issued(dump),
            "downloads": downloads(dump),
            "languages": languages(dump),
            "authors": authors(dump),
            "files": files(dump),
            "subjects": subjects(dump),
            "categories": categories(dump),
        }

        return _book
    else:
        return None

# creates a folder with {path}/cache/epub/{id}/{id}.rdf filled with the newest info
def fetch_rdfs(path: str):

    with requests.get(
        "https://www.gutenberg.org/cache/epub/feeds/rdf-files.tar.bz2", stream=True
    ) as r:
        with open(path + "/rdf-files.tar.bz2", "wb") as f:
            copyfileobj(r.raw, f)

    with tarfile.open(path + "/rdf-files.tar.bz2", "r") as tar:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(tar, path)

    os.remove(path + "/rdf-files.tar.bz2")

def remove_bogus(bogus: list, path: str):
    with alive_bar(len(bogus), title="Removing known bogus books",bar="classic", spinner="classic") as bar:
        for _id in bogus:
            file = "{}/cache/epub/{}".format(path, _id)
            if os.path.exists(file):
                rmtree(file)
            bar()


def json_dump(books: list, _file: str ):
    with open(_file, "x") as out:
        json.dump(books, out)


def sqlite_dump(books: list, _db: str):
    conn = sqlite3.connect("gutenberg.new")
    c = conn.cursor()
    c.executescript(
        """CREATE TABLE IF NOT EXISTS "Book" (
    "ID"	INTEGER NOT NULL UNIQUE,
    "title"	TEXT NOT NULL,
    "description"	TEXT,
    "issued"	TEXT NOT NULL,
    "downloads"	INTEGER NOT NULL,
    "json"  TEXT NOT NULL,
    PRIMARY KEY("ID")
);

CREATE TABLE IF NOT EXISTS "Languages" (
    "ID"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
    "Book_ID"	INTEGER NOT NULL,
    "language"	TEXT NOT NULL,
    FOREIGN KEY("Book_ID") REFERENCES "Book"("ID")
);

CREATE TABLE IF NOT EXISTS "Authors" (
    "ID"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
    "Book_ID"	INTEGER NOT NULL,
    "name"	TEXT NOT NULL,
    "birth"	INTEGER,
    "death"	INTEGER,
    "page"	TEXT,
    FOREIGN KEY("Book_ID") REFERENCES "Book"("ID")
);

CREATE TABLE IF NOT EXISTS "Aliases" (
    "ID"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
    "Author_ID"	INTEGER NOT NULL,
    "alias"	TEXT NOT NULL,
    FOREIGN KEY("Author_ID") REFERENCES "Authors"("ID")
);

CREATE TABLE IF NOT EXISTS "Files" (
    "ID"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
    "Book_ID"	INTEGER NOT NULL,
    "url"	TEXT NOT NULL,
    "modified"	TEXT NOT NULL,
    "size"	INTEGER NOT NULL,
    FOREIGN KEY("Book_ID") REFERENCES "Book"("ID")
);

CREATE TABLE IF NOT EXISTS "Subjects" (
    "ID"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
    "Book_ID"	INTEGER NOT NULL,
    "subject"	TEXT NOT NULL,
    FOREIGN KEY("Book_ID") REFERENCES "Book"("ID")
);

CREATE TABLE IF NOT EXISTS "Categories" (
    "ID"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
    "Book_ID"	INTEGER NOT NULL,
    "category"	TEXT NOT NULL,
    FOREIGN KEY("Book_ID") REFERENCES "Book"("ID")
);"""
    )
    conn.commit()

    with alive_bar(len(books), title="Dumping books in a database", bar="classic", spinner="classic") as bar:
        for book in books:
            c.execute(
                'INSERT INTO Book ("ID","title","description","issued","downloads","json") VALUES (?,?,?,?,?,?);',
                [
                    book["id"],
                    book["title"],
                    book["description"],
                    book["issued"],
                    book["downloads"],
                    json.dumps(book)
                    ]
            )

            for language in book["languages"]:
                c.execute(
                    'INSERT INTO Languages ("Book_ID","language") VALUES (?,?);',
                    (book["id"], language)
                )

            for author in book["authors"]:
                c.execute(
                    'INSERT INTO Authors ("Book_ID","name","birth","death","page") VALUES (?,?,?,?,?);',
                    [
                        book["id"],
                        author["name"],
                        author["birth"],
                        author["death"],
                        author["page"]
                        ]
                )
                author_id = c.lastrowid
                for alias in author["aliases"]:
                    c.execute(
                        'INSERT INTO Aliases ("Author_ID","alias") VALUES (?,?);',
                        [author_id, alias]
                    )

            for _file in book["files"]:
                c.execute(
                    'INSERT INTO Files ("Book_ID","url","modified","size") VALUES (?,?,?,?);',
                    [book["id"], _file["url"], _file["modified"], _file["size"]]
                )

            for subject in book["subjects"]:
                c.execute(
                    'INSERT INTO Subjects ("Book_ID","subject") VALUES (?,?);',
                    [book["id"], subject]
                )

            for category in book["categories"]:
                c.execute(
                    'INSERT INTO Categories ("Book_ID","category") VALUES (?,?);',
                    [book["id"], category]
                )

            bar()
    print("Commiting it to memory")
    conn.commit()
    os.rename("gutenberg.new", _db )

def main():
    if len(sys.argv) == 3 and (sys.argv[1] == "--sqlite" or sys.argv[1] == "--json"):
        with tempfile.TemporaryDirectory() as temp:
            print("Fetching the archive")
            fetch_rdfs(temp)
            remove_bogus([38200, 58872, 61736, 90907], temp)
            books = os.listdir(temp + "/cache/epub")
            ids = sorted([ int(re.search(r"\d+", book).group(0)) for book in books])

            books = []

            with alive_bar(len(ids), title="Loading books",bar="classic", spinner="classic") as bar:
                for _id in ids:
                    try:
                        bar.text( "procesing " + str(_id) )
                        _book = get_book(_id, temp)
                        if _book != None:
                            books.append(_book)
                        else:
                            print( "id {} returned None".format(_id) )
                    except:
                        print( "id {} failed to parse".format(_id) )
                    bar()

            if sys.argv[1] == "--sqlite":
                sqlite_dump(books, sys.argv[2])
            elif sys.argv[1] == "--json":
                json_dump(books, sys.argv[2])
    else:
        print("--sqlite <file>, for an sqlite database>")
        print("--json <file>, for a json file")


if __name__ == "__main__":
    main()
