from abc import ABC, abstractmethod


class Email(ABC):

    @abstractmethod
    def authenticate(self):
        pass
    
    @abstractmethod
    def send_mail(self):
        pass