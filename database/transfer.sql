create table IF NOT EXISTS `transfer` (
  `ID` int(11) NOT NULL auto_increment,
  `Card` int(11) NOT NULL,
  primary key(`id`)
) default charset = utf8;