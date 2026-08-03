from rest_framework import status



formatReponse = {
    'type': str or None,
    'titre': str or None,
    'message': str or None,
    'niveau': str or 1,
    'status': int or None
}

def request_header_token(request):
    formatReponse['type'] = 'error'
    formatReponse['titre'] = 'Informations Manquantes'
    formatReponse['niveau'] = 100
    formatReponse['message'] = ""
    formatReponse['status'] = int(status.HTTP_400_BAD_REQUEST)
    data = None
    if request.headers.get('Authorization') and request.headers.get('Authorization').split(' ')[1] != None:
        data = request.headers.get('Authorization').split(' ')[1]
    return data, formatReponse


def minute_to_seconde(minute):
    return minute * 60



