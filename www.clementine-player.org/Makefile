LANGUAGES=de hu it pt ru sk es fr pt_BR sv uk vi sl fi

all: pot $(addprefix mo-,${LANGUAGES})

pot:
	django-admin makemessages -v 0 -l pot
	mv locale/pot/LC_MESSAGES/django.po locale/django.pot
	rmdir locale/pot/LC_MESSAGES
	rmdir locale/pot

mo-%: po-%
	msgfmt locale/$*/LC_MESSAGES/django.po -o locale/$*/LC_MESSAGES/django.mo

po-%:
	ln -fs `pwd`/locale/$*.po locale/$*/LC_MESSAGES/django.po
	django-admin makemessages -v 0 -l $*
