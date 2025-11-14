if you are using vs code terminal you have to open 3 terminals and and you have to run command 
rasa_env\scripts\activate --> this command helps to re-activate the vistual enviornment that is required for rasa.
then on terminal 1 you have to run command --> rasa run actions (it helps to run the action server)
then on terminal 2 you have to run command --> rasa run -m models --enable-api --cors "*" (Starts the Rasa chatbot backend)
then on terminal 3 --> uvicorn main:app --reload (Starts your FastAPI + frontend bridge)
