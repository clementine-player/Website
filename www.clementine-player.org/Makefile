LANGUAGES=de hu it pt ru sk es fr pt_BR sv uk vi sl fi br cs et ia nn tr ca hr lt el ka uz eu nl pl zh_CN da af be ko ja ga bg zh_TW my id ar gl lv fa

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
	django-admin makemessages --no-wrap -v 0 -l $*

static/css/all.css: $(wildcard css/*.css)
	java -jar closure-stylesheets-20111230.jar \
		--allow-unrecognized-functions \
		--pretty-print $(wildcard css/*.css) \
		--output-file static/css/all.css

static/css/all-rtl.css: $(wildcard css/*.css)
	java -jar closure-stylesheets-20111230.jar \
		--allow-unrecognized-functions \
		--output-orientation RTL \
		--define RTL_LANG \
		--pretty-print $(wildcard css/*.css) \
		--output-file static/css/all-rtl.css

css: static/css/all.css static/css/all-rtl.css

clean:
	rm -f static/css/all.css static/css/all-rtl.css
