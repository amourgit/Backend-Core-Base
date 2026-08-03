from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User

class CustomUserCreationForm(UserCreationForm):
    """
    Formulaire personnalisé pour la création d'utilisateur.
    """
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone_number',
                 'address', 'profile_picture', 'date_of_birth', 'language_preference',
                 'timezone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rendre les champs optionnels
        for field in self.fields:
            self.fields[field].required = False

class CustomUserChangeForm(UserChangeForm):
    """
    Formulaire personnalisé pour la modification d'utilisateur.
    """
    class Meta(UserChangeForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone_number',
                 'address', 'profile_picture', 'date_of_birth', 'language_preference',
                 'timezone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rendre les champs optionnels
        for field in self.fields:
            self.fields[field].required = False 