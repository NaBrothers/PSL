create table IF NOT EXISTS `items` (
  `ID` smallint(6) NOT NULL auto_increment,
  `User` bigint NOT NULL,
  `Type` int(11) default null,
  `Item` int(11) default null,
  `Count` int(11) default null,
  primary key(`ID`)
) default charset = utf8;