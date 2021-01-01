create table IF NOT EXISTS `offline` (
  `ID` smallint(6) NOT NULL auto_increment,
  `User` bigint NOT NULL,
  `Message` varchar(256) default null,
  primary key(`ID`)
) default charset = utf8;