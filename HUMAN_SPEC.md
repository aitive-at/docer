Ok this project is going to be an LLM/Vision base document scanning and data extraction application. It will be both deployed on premise and in the cloud. 

For inference connect to the OLLAMA api for now and use gemma4 as the model of choice. 
Document scanning should be queued and executed async, with progress being reported to the user.

Now on to the scanning, we use the visual llm to scan the images ( extracted from pdfs etc or directly uploaded ), and want to get structed scan output back. Provide insighed into the process and a view of the queued scans. 

Now comes the tricky part: The actual data extraction process. Each scanner would be resonpsible for a specific document type e.g invoices, offers or others.

The user can configure what fields they want to extract and how, if they are required etc and what data types they should be. The data should all be normalized and canonicalized, returning the original value and the canonicalized version. 

The schema for extraction is hierarchical, there are top level fields, but also there can be a list of order lines where each order line has fields too, or a single sub object that models an adress. For field data types we need quite a lot of high level data types e.g but not limited too:

name, street name, zip code, iban, uid, int, decimal,float, text, email adress, currency amount with currency, quantity with unit  etc... think of any you might need, and keep in mind we need to canonicalize them. Field definitions can also have hints specified to aid the llm with extraction. Note that everything needs to be multilingual. Note that the data is consumed by various downstream systems and e.g a name needs to be canonicalized for comparison etc.. so not to get lots of duplicates differing in only small parts.

We also need categorical values where the user specifies an id and a value and the scanner returns the id. THese need to be defined in the scanner configuration as well. Think enums. Also we need open enums where the scanner can add new values with new ids when none of the extisting ones match.

Also the scanner itself needs a priming prompt part, to describe what documents are going to be scanned... to help with thinking. 

When scanning field errors should be reported as well what attempts were made. Use the LLM for all fuzzy tasks again. 

Again think about the hierarchical schema with nested sub objects or even lists of objects ( e.g order lines )

Give the user visual feedback about a scan .. maybe render the image with the data extracted marked if that is possible ? 

Everything has to work from the api as well. 

We want both a web frontend for interactive/configuration use and an API for programatic use. PDFs and most image forms should be supported as input formats, Files should be stored and de duplicated of course.

Logically there will be "Accounts" which are tenants. Each Account can have multiple "Scanners" that can be configured. They are isolated from each other. This facilitates the cloud model where users can have an account and multiple scanners.

The database models should be isolated, but only soft isolation with account_id or similar measures. Urls should be scoped to accounts of course e.g /myaccount/myscanner etc..

There should be an account dashboard and admin page of course, and scanners can be created, editited etc... 

On scans there should be clear results with clear error messages on what went wrong. 
Users can sign up easily ( for now with no confirmation ) and get a personal account.
They can also create organizational accounts that users can be given access to ... think the github model of account management. API keys can be created for an account and user with the REST Api. Scans should be tracked at the account level so we know how many pages where scanned by an account ( for billing later ), with clear output in the account dashboard as well.


Use Django 6.0 as the web framework and sqlite for now as the database for local development

For the frontend use HTMLX or a similar library to make it more interactive, especially
for progress panels which should receive live updates.

For styling, look at https://aitivedata.com, which is my company website.
Style the whole application frontend like that so it matches the corporate CI.

Use uv for anything python related from package management to running tools and scripts. Nothing outside of uv please. Use a modern python version.

For testing i want full e2e tests as well i can run as smoke tests, starting all applicaiton parts, creating an accoutn and scanner, uploading a document, scanning it and comparing the results to known good data. This should be done extensible so that i can just drop a pdf in a folder and specify the known good extraction results, so we can easily add regression tests lateron that work e2e. Run these tests to make sure everything works before completing your implementation.

I have added one pdf to the folder tests/data and a scenarios.json describing the test... Change that as you like, its an example.
