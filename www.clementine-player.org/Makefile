LANGUAGES=de hu it pt ru sk es fr pt_BR sv uk vi sl fi br cs et ia nn tr ca hr lt el ka uz eu nl pl zh_CN da af be ko ja ga bg zh_TW my id ar gl lv fa sr sr@latin ms ro he is

all: pot $(addprefix mo-,${LANGUAGES}) css

pot:
	django-admin makemessages --no-wrap -v 0 -l pot
	mv locale/pot/LC_MESSAGES/django.po locale/django.pot
	rmdir locale/pot/LC_MESSAGES
	rmdir locale/pot

mo-%: po-%
	msgfmt locale/$*/LC_MESSAGES/django.po -o locale/$*/LC_MESSAGES/django.mo

po-%:
	-mkdir -p locale/$*/LC_MESSAGES/
	ln -fs `pwd`/locale/$*.po locale/$*/LC_MESSAGES/django.po
	django-admin makemessages --no-wrap --keep-pot -v 0 -l $*

# One stylesheet for every language: right-to-left pages are laid out by the
# same rules (see css/style.css), so it's just the files one after another.
static/css/all.css: $(sort $(wildcard css/*.css))
	cat $^ > $@

css: static/css/all.css

clean:
	rm -f static/css/all.css
