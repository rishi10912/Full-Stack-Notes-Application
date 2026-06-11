from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework import generics
from .serializers import UserSerializer, NoteSerializer
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Note

# Create your views here.
class NoteListCreate(generics.ListCreateAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated] #Only authenticated users can access this view
    def get_queryset(self):
        user = self.request.user
        return Note.objects.filter(author=user) #Only return notes that belong to the authenticated user
    
    def perform_create(self, serializer):
        if serializer.is_valid():
            serializer.save(author=self.request.user) 
        else:
            print(serializer.errors)
class NoteDelete(generics.DestroyAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated] #Only authenticated users can access this view
    
    def get_queryset(self):
        user = self.request.user
        return Note.objects.filter(author=user) #Only allow users to delete their own notes

class CreateUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer 
    permission_classes = [AllowAny] #Anyone can create an account
    
