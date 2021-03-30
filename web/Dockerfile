FROM php:7.2-apache

ENV HOST=

COPY . /var/www/html/

RUN pecl install mongodb \
    &&  echo "extension=mongodb.so" > /usr/local/etc/php/conf.d/mongo.ini
