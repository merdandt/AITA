AUTH_TASK = """
            - Open the URL: {url}
            - Authenticate using the following credentials:
            - Enter email: {ms_email}
            - Enter password: {ms_password}
            - Wait for User to approve login on Authenticator app. Do not proceed until approved.
            - Ensure you land on the SpeedGrader page for the first student.
        """
        
ANALIZE_TEXT = """
Tel me if this text is positive, offensive  or negative
Text:
{text}

For example:
```positive```,
```negative```
or ```offensive```
"""
